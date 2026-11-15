"""Compute the vectors of a document version's passages (worker job).

The sync cuts a new version into passages in its own transaction (fast)
and queues the job "document.embed" for that version. This job is slow
(a model runs over every passage), so it is separate: a failure here
never undoes a sync, and it is retried with growing delays.
"""

import logging
import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.background_job import BackgroundJob
from app.models.document import Document, DocumentVersion
from app.models.document_chunk import DocumentChunk
from app.services.embeddings import embeddings_enabled, get_embedder, vector_literal
from app.services.job_queue import enqueue_job, job_handler


logger = logging.getLogger("eka.embeddings")

EMBED_JOB = "document.embed"
BATCH_SIZE = 32


def request_embeddings(db: Session, *, version: DocumentVersion) -> None:
    """Worker side, inside the sync: queue the vectors of this version."""
    if not embeddings_enabled():
        return
    enqueue_job(
        db,
        organization_id=version.organization_id,
        kind=EMBED_JOB,
        created_by_user_id=None,
        payload={"version_id": str(version.id)},
        dedupe_key=f"embed:{version.id}",
    )


INSERT_SQL = text("""
    INSERT INTO chunk_embeddings
        (chunk_id, model, organization_id, document_id, dims, embedding, created_at)
    VALUES
        (:chunk_id, :model, :organization_id, :document_id, :dims,
         CAST(:embedding AS vector), now())
""")


def embed_version(db: Session, *, version_id: uuid.UUID) -> int:
    """Vectors for every passage of this version; returns how many."""
    version = db.get(DocumentVersion, version_id)
    if version is None:
        return 0
    document = db.get(Document, version.document_id)
    if document is None or document.current_version_id != version.id:
        # A newer version replaced it before its turn: nothing to do.
        return 0

    embedder = get_embedder()
    chunks = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.version_id == version.id)
        .order_by(DocumentChunk.ordinal)
    ).all()

    db.execute(
        text(
            "DELETE FROM chunk_embeddings WHERE model = :model AND chunk_id IN "
            "(SELECT id FROM document_chunks WHERE version_id = :version_id)"
        ),
        {"model": embedder.model, "version_id": version.id},
    )
    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        vectors = embedder.embed_passages(
            [f"{c.heading}\n{c.content}" if c.heading else c.content for c in batch]
        )
        db.execute(
            INSERT_SQL,
            [
                {
                    "chunk_id": chunk.id,
                    "model": embedder.model,
                    "organization_id": chunk.organization_id,
                    "document_id": chunk.document_id,
                    "dims": embedder.dims,
                    "embedding": vector_literal(vector),
                }
                for chunk, vector in zip(batch, vectors)
            ],
        )
    db.flush()
    logger.info("embedded version %s: %d passages", version.id, len(chunks))
    return len(chunks)


@job_handler(EMBED_JOB)
def run_embed_job(db: Session, job: BackgroundJob) -> None:
    embed_version(db, version_id=uuid.UUID(job.payload["version_id"]))
