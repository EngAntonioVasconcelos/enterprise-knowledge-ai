"""Measure the answers with the configured language model (AJ-1).

Runs the Atlantico Logistica questions through answer_question (search with
the reranker, the versioned prompt, the model, the checks) in the
disposable test database (eka_test), inside a transaction that is rolled
back: nothing is kept. Prints, per question group, how many answers were
correct, wrong, abstained or refused by the checks, the leaks (must be 0)
and the time per answer, then a few answers to read. The numbers are saved
in var/eval/ (ignored by Git).

Needs a model: LLM_PROVIDER=openai_compatible with LLM_BASE_URL and
LLM_MODEL in your .env (docs/development/answers.md). With a hosted provider
the questions and passages of the fictional company are sent to it. A local
model on a CPU can take tens of seconds per answer: start with --limit 10.

Run from the backend folder, with the test database running:
    python -m scripts.evaluate_answers --limit 10
Compare prompt versions on the same questions (AJ-1b, about 20 minutes per
version for the 60 questions on a laptop CPU):
    python -m scripts.evaluate_answers --prompts v1,v2
The held-out questions (Phase 9), never used to tune anything, say whether
the numbers hold up on questions nobody optimised for:
    python -m scripts.evaluate_answers --questions holdout
"""

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.services.llm import LLMUnavailableError, get_chat_model
from app.services.answer_service import PROMPT_NAME, PROMPT_VERSIONS
from app.services.prompts import load_prompt
from scripts.prepare_test_database import TEST_ADMIN_URL
from tests.integration import test_document_permissions as permissions
from tests.integration.answer_harness import evaluate_answers, format_answer_report
from tests.integration.retrieval_distractors import with_distractors
from tests.integration.retrieval_harness import ingest, load_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure the answers.")
    parser.add_argument("--library", choices=("small", "large"), default="small")
    parser.add_argument("--limit", type=int, default=None, help="only the first N questions")
    parser.add_argument(
        "--questions",
        choices=("main", "holdout"),
        default="main",
        help="main: the questions tuned against; holdout: new ones, never tuned against",
    )
    parser.add_argument(
        "--prompts",
        default=settings.ANSWER_PROMPT_VERSION,
        help="prompt versions to compare on the same questions, e.g. v1,v2",
    )
    args = parser.parse_args()

    if make_url(TEST_ADMIN_URL).database != "eka_test":
        print("PAROU: this evaluation runs only on the test database eka_test.")
        return 1
    try:
        model = get_chat_model().model
    except LLMUnavailableError as exc:
        print(f"PAROU: {exc}. See docs/development/answers.md.")
        return 1
    versions = [v.strip() for v in args.prompts.split(",") if v.strip()]
    unknown = [v for v in versions if v not in PROMPT_VERSIONS]
    if unknown or not versions:
        print(f"PAROU: unknown prompt versions {unknown}; known: {', '.join(PROMPT_VERSIONS)}")
        return 1
    prompt_ids = {v: load_prompt(PROMPT_NAME, v).prompt_id for v in versions}
    print(
        f"Model: {model} ({settings.LLM_PROVIDER}), seed {settings.LLM_SEED}, "
        f"prompts {', '.join(prompt_ids.values())}, reranker {settings.ANSWER_RERANK}"
    )

    dataset = load_dataset(args.questions)
    if args.library == "large":
        dataset = with_distractors(dataset)
    engine = create_engine(TEST_ADMIN_URL)
    connection = engine.connect()
    transaction = connection.begin()
    db = sessionmaker(bind=connection, autoflush=False, join_transaction_mode="create_savepoint")()
    try:
        db.execute(text("SET ROLE eka_runtime"))
        world = permissions.World(db)
        with tempfile.TemporaryDirectory(prefix="eka-eval-") as storage:
            started = time.perf_counter()
            ingest(db, world, dataset, Path(storage))
            print(
                f"Library ready ({len(dataset['documents'])} documents) in {time.perf_counter() - started:.1f} s; "
                f"questions: {args.questions}"
            )
            count = args.limit or len(dataset["questions"])
            results = {}
            for version in versions:
                print(f"Asking {count} questions with prompt {version}...", flush=True)
                started = time.perf_counter()
                results[version] = evaluate_answers(
                    db, world, dataset, limit=args.limit, prompt_version=version
                )
                print(f"  done in {(time.perf_counter() - started) / 60:.1f} min", flush=True)
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()

    for version, result in results.items():
        print(f"\n===== prompt {prompt_ids[version]} =====\n")
        print(format_answer_report(result))
        print("\nAnswers to read (not correct first):")
        for sample in result["samples"]:
            print(f"\n  [{sample['outcome']}] {sample['query']}\n  -> {sample['answer']}")
            for issue in sample["issues"]:
                print(f"     check: {issue}")
            if sample.get("draft"):
                print(f"     refused draft: {sample['draft']}")

    out = Path("var/eval")
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"answers-{args.questions}-{args.library}-{model.replace('/', '_').replace(':', '_')}-{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "model": model,
                "seed": settings.LLM_SEED,
                "library": args.library,
                "questions": args.questions,
                "prompts": prompt_ids,
                "results": results,
            },
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved: {path}")
    return 0 if all(r["leaks"] == 0 for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
