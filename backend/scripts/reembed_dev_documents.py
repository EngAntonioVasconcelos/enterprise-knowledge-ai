"""Compute vectors with the configured embedding model for every current
document version of the development database (AJ-2b).

Changing EMBEDDING_MODEL does not touch existing vectors: each vector
records its model, and search uses only the configured one. Documents
synced before the change have no vectors of the new model, so search by
meaning skips them until this script (or a new sync) computes them; search
by words still finds them meanwhile.

Development only: it refuses any database other than the development one
on port 1996, and needs the administrator account of that database (a
superuser there), because it reads every organization at once. Production
gets a worker job for this in Phase 10. Nothing secret is printed.

Run from the backend folder, in the container:
    docker compose -f ../infrastructure/dev/docker-compose.yml run --rm backend python -m scripts.reembed_dev_documents
"""

import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.embedding_service import embed_version
from app.services.embeddings import EmbeddingUnavailableError, get_embedder


DEV_PORT = 1996


def check_target(url: str | None) -> str | None:
    """None when the target is acceptable, otherwise the reason it is not."""
    if not url:
        return "MIGRATION_DATABASE_URL is not set"
    if make_url(url).port != DEV_PORT:
        return f"only the development database on port {DEV_PORT} is allowed"
    return None


def main() -> int:
    problem = check_target(settings.MIGRATION_DATABASE_URL)
    if problem:
        print(f"PAROU: {problem}.")
        return 1
    try:
        embedder = get_embedder()
    except EmbeddingUnavailableError as exc:
        print(f"PAROU: {exc}")
        return 1
    print(f"Model: {embedder.model} ({embedder.dims} numbers per text)")

    engine = create_engine(settings.MIGRATION_DATABASE_URL)
    try:
        with Session(engine) as db:
            if not db.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar():
                print("PAROU: the administrator account of the development database must be a superuser.")
                return 1
            versions = db.execute(
                text(
                    "SELECT d.current_version_id FROM documents AS d "
                    "WHERE d.current_version_id IS NOT NULL AND d.status = 'active' "
                    "AND NOT EXISTS (SELECT 1 FROM chunk_embeddings AS e "
                    "  JOIN document_chunks AS c ON c.id = e.chunk_id "
                    "  WHERE c.version_id = d.current_version_id AND e.model = :model)"
                ),
                {"model": embedder.model},
            ).scalars().all()
            print(f"Documents without vectors of this model: {len(versions)}")
            started, passages = time.perf_counter(), 0
            for number, version_id in enumerate(versions, start=1):
                passages += embed_version(db, version_id=version_id)
                db.commit()
                print(f"  {number}/{len(versions)} done", flush=True)
            print(f"Computed {passages} vectors in {time.perf_counter() - started:.1f} s")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
