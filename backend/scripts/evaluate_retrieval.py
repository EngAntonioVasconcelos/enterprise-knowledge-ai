"""Measure search quality with the configured embedding model (AI-1).

Runs the Atlantico Logistica dataset (tests/evaluation) through the real
pipeline in the disposable test database (eka_test), inside a transaction
that is rolled back: nothing is kept. Prints Recall@5 and MRR@10 per search
mode and question group, the leaks (must be 0), the time per search, and
the questions each mode missed. A copy of the numbers is saved in
var/eval/ (ignored by Git) to compare future changes.

Run from the backend folder, with the test database running and the
model downloaded (python -m scripts.try_embeddings):
    python -m scripts.evaluate_retrieval
"""

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
from app.services.embeddings import EmbeddingUnavailableError, get_embedder
from scripts.prepare_test_database import TEST_ADMIN_URL
from tests.integration import test_document_permissions as permissions
from tests.integration.retrieval_harness import (
    evaluate,
    format_report,
    ingest,
    load_dataset,
)


def main() -> int:
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

    dataset = load_dataset()
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
            results = evaluate(db, world, dataset)
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()

    print()
    print(format_report(results))
    for mode, result in results.items():
        if result.get("available") and result["misses"]:
            print(f"\nMissed by {mode} (not in the first 5):")
            for miss in result["misses"]:
                print(f"  rank {miss['rank'] or '-':>2}  {miss['query']}")

    out = Path("var/eval")
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"retrieval-{model.replace('/', '_')}-{stamp}.json"
    path.write_text(json.dumps({"model": model, "results": results}, indent=1), encoding="utf-8")
    print(f"\nSaved: {path}")
    return 0 if all(r.get("leaks", 0) == 0 for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
