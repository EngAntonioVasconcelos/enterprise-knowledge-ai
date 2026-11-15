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
from app.services.prompts import load_prompt
from app.services.answer_service import PROMPT
from scripts.prepare_test_database import TEST_ADMIN_URL
from tests.integration import test_document_permissions as permissions
from tests.integration.answer_harness import evaluate_answers, format_answer_report
from tests.integration.retrieval_distractors import with_distractors
from tests.integration.retrieval_harness import ingest, load_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure the answers.")
    parser.add_argument("--library", choices=("small", "large"), default="small")
    parser.add_argument("--limit", type=int, default=None, help="only the first N questions")
    args = parser.parse_args()

    if make_url(TEST_ADMIN_URL).database != "eka_test":
        print("PAROU: this evaluation runs only on the test database eka_test.")
        return 1
    try:
        model = get_chat_model().model
    except LLMUnavailableError as exc:
        print(f"PAROU: {exc}. See docs/development/answers.md.")
        return 1
    prompt_id = load_prompt(*PROMPT).prompt_id
    print(f"Model: {model} ({settings.LLM_PROVIDER}), prompt {prompt_id}, reranker {settings.ANSWER_RERANK}")

    dataset = load_dataset()
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
            print(f"Library ready ({len(dataset['documents'])} documents) in {time.perf_counter() - started:.1f} s")
            count = args.limit or len(dataset["questions"])
            print(f"Asking {count} questions...")
            result = evaluate_answers(db, world, dataset, limit=args.limit)
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()

    print()
    print(format_answer_report(result))
    print("\nA few answers to read:")
    for sample in result["samples"]:
        print(f"\n  [{sample['outcome']}] {sample['query']}\n  -> {sample['answer']}")
        for issue in sample["issues"]:
            print(f"     check: {issue}")

    out = Path("var/eval")
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"answers-{args.library}-{model.replace('/', '_').replace(':', '_')}-{stamp}.json"
    path.write_text(
        json.dumps({"model": model, "prompt": prompt_id, "library": args.library, **result}, indent=1),
        encoding="utf-8",
    )
    print(f"\nSaved: {path}")
    return 0 if result["leaks"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
