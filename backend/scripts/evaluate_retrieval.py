"""Measure search quality with the configured models (AI-1, AI-2, AI-2b).

Runs the Atlantico Logistica dataset (tests/evaluation) through the real
pipeline in the disposable test database (eka_test), inside a transaction
that is rolled back: nothing is kept.

By default the library is the large one: the 17 documents plus 400
distractors that share words with the questions without answering them
(tests/integration/retrieval_distractors.py), so the numbers are closer to
a real company. --library small uses only the 17 documents.

Compares words, meaning, hybrid (weighted fusion) and hybrid with the
reranker as configured (RERANK_CANDIDATES, RERANK_MAX_CHARS). With
--compare-rerank it also measures the reranker with 20 or 10 candidates,
whole passages or their first 600 characters (much slower: each reranker
variant reads every question's candidates on the CPU).
Prints Recall@5 and MRR@10 per variant and question group, leaks (must be
0), the average and 95th percentile time per search, and the questions
each variant missed. The numbers are saved in var/eval/ (ignored by Git).

Run from the backend folder, with the test database running and the
models downloaded (python -m scripts.try_embeddings and
python -m scripts.try_reranker). About 2 to 3 minutes on a laptop CPU:
    python -m scripts.evaluate_retrieval
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
from app.services.embeddings import E5_MODELS, EmbeddingUnavailableError, get_embedder
from app.services.reranking import RerankUnavailableError, get_reranker
from scripts.prepare_test_database import TEST_ADMIN_URL
from tests.integration import test_document_permissions as permissions
from tests.integration.retrieval_distractors import with_distractors
from tests.integration.retrieval_harness import (
    RERANK_VARIANTS,
    evaluate,
    format_report,
    ingest,
    load_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure search quality.")
    parser.add_argument("--library", choices=("large", "small"), default="large")
    parser.add_argument(
        "--compare-rerank", action="store_true", help="also the four reranker settings (slow)"
    )
    parser.add_argument(
        "--embedding-model",
        choices=sorted(E5_MODELS),
        help="measure another embedding model (download it first with try_embeddings --model)",
    )
    args = parser.parse_args()
    if args.embedding_model:
        settings.EMBEDDING_MODEL = args.embedding_model
    if make_url(TEST_ADMIN_URL).database != "eka_test":
        print("PAROU: this evaluation runs only on the test database eka_test.")
        return 1
    try:
        embedder = get_embedder()
        model = embedder.model
    except EmbeddingUnavailableError as exc:
        print(f"Embeddings unavailable ({exc}); only search by words is measured.")
        model = "none"
    print(f"Embedding provider: {settings.EMBEDDING_PROVIDER} ({model})")
    try:
        started = time.perf_counter()
        loaded = get_reranker()
        loaded.score("warm up", ["so the first question is not timed loading"])
        reranker = loaded.model
        print(f"Reranker: {reranker}, loaded in {time.perf_counter() - started:.1f} s")
    except RerankUnavailableError as exc:
        reranker = "none"
        print(f"Reranker unavailable ({exc}); the rerank variants are not measured.")

    dataset = load_dataset()
    if args.library == "large":
        dataset = with_distractors(dataset)
    variants = ("keyword", "semantic", "hybrid", "hybrid+rerank")
    if args.compare_rerank:
        variants += tuple(RERANK_VARIANTS)
    engine = create_engine(TEST_ADMIN_URL)
    connection = engine.connect()
    transaction = connection.begin()
    db = sessionmaker(
        bind=connection, autoflush=False, join_transaction_mode="create_savepoint"
    )()
    try:
        db.execute(text("SET ROLE eka_runtime"))
        world = permissions.World(db)
        with tempfile.TemporaryDirectory(prefix="eka-eval-") as storage:
            started = time.perf_counter()
            embedded = ingest(db, world, dataset, Path(storage))
            print(
                f"Ingested {len(dataset['documents'])} documents, {embedded} passages "
                f"with vectors, in {time.perf_counter() - started:.1f} s"
            )
            print(f"Asking {len(dataset['questions'])} questions x {len(variants)} variants...")
            results = evaluate(db, world, dataset, modes=variants)
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()

    print()
    print(format_report(results))
    for mode, result in results.items():
        if mode in ("keyword", "semantic"):
            continue
        if result.get("available") and result["misses"]:
            print(f"\nMissed by {mode} (not in the first 5):")
            for miss in result["misses"]:
                print(f"  rank {miss['rank'] or '-':>2}  {miss['query']}")
                print(f"           first: {' | '.join(miss['first'])}")

    out = Path("var/eval")
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"retrieval-{args.library}-{model.replace('/', '_')}-{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "library": args.library,
                "documents": len(dataset["documents"]),
                "model": model,
                "reranker": reranker,
                "results": results,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved: {path}")
    return 0 if all(r.get("leaks", 0) == 0 for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
