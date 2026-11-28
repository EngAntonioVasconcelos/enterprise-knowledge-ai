"""Queue the vectors that are missing for the configured embedding model.

Each document version gets its vectors from a worker job (document.embed).
When that job fails for good (for example, the model was not downloaded on
the server yet) or EMBEDDING_MODEL changes, the document stays searchable
by words, but search by meaning skips it. This script finds every current
version without vectors of the configured model and queues the job again,
through the same path a sync uses; the worker then computes the vectors.

It only adds jobs: it never deletes or changes documents, passages or
vectors, and it skips versions that already have a job waiting or running.
Without --apply it only counts. It needs the administrator account
(MIGRATION_DATABASE_URL), because it reads every organization at once.
Nothing secret is printed.

Production, in infrastructure/prod:
    docker compose --profile setup run --rm migrate python -m scripts.queue_missing_embeddings
    docker compose --profile setup run --rm migrate python -m scripts.queue_missing_embeddings --apply
"""

import argparse
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import DocumentVersion
from app.services.embedding_service import EMBED_JOB, request_embeddings
from app.services.embeddings import embeddings_enabled


MISSING_SQL = text("""
    SELECT d.current_version_id
    FROM documents AS d
    WHERE d.current_version_id IS NOT NULL
      AND d.status = 'active'
      AND NOT EXISTS (
          SELECT 1 FROM chunk_embeddings AS e
          JOIN document_chunks AS c ON c.id = e.chunk_id
          WHERE c.version_id = d.current_version_id AND e.model = :model)
      AND NOT EXISTS (
          SELECT 1 FROM background_jobs AS j
          WHERE j.kind = :kind
            AND j.status IN ('queued', 'running')
            AND j.payload ->> 'version_id' = d.current_version_id::text)
    ORDER BY d.current_version_id
""")


def missing_versions(db: Session, *, model: str) -> list:
    """Current versions with no vectors of this model and no job waiting."""
    return list(db.execute(MISSING_SQL, {"model": model, "kind": EMBED_JOB}).scalars())


def queue_missing(db: Session, *, model: str) -> int:
    """Queue one document.embed job per version found; returns how many."""
    versions = missing_versions(db, model=model)
    for version_id in versions:
        request_embeddings(db, version=db.get(DocumentVersion, version_id))
    db.flush()
    return len(versions)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="queue the jobs (otherwise only count)")
    args = parser.parse_args(argv)

    if not embeddings_enabled():
        print("PAROU: EMBEDDING_PROVIDER is 'none'; there is nothing to compute.")
        return 1
    if not settings.MIGRATION_DATABASE_URL:
        print("PAROU: MIGRATION_DATABASE_URL is not set.")
        return 1

    model = settings.EMBEDDING_MODEL
    engine = create_engine(settings.MIGRATION_DATABASE_URL)
    try:
        with Session(engine) as db:
            if not db.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar():
                print("PAROU: this needs the administrator account of the database.")
                return 1
            if not args.apply:
                count = len(missing_versions(db, model=model))
                print(f"Model: {model}")
                print(f"Documents without vectors and without a job waiting: {count}")
                if count:
                    print("Nothing was changed. Run again with --apply to queue them.")
                return 0
            count = queue_missing(db, model=model)
            db.commit()
            print(f"Model: {model}")
            print(f"Queued {count} vector jobs; the worker computes them in the next minutes.")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
