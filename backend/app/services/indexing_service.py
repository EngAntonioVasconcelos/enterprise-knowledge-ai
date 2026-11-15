"""Turn a document version into searchable chunks (Phase 6, RAG Core).

Runs inside the sync, in the worker, right after a new version becomes
current: chunking is fast and needs no model. Vectors (next step) are
computed later by their own job, because they are slow.
"""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.document import DocumentVersion
from app.models.document_chunk import DocumentChunk
from app.services.chunking import chunk_text


def index_version(db: Session, *, version: DocumentVersion, text: str) -> int:
    """Replace the chunks of this version; returns how many were made."""
    db.execute(delete(DocumentChunk).where(DocumentChunk.version_id == version.id))
    chunks = chunk_text(text)
    db.add_all(
        DocumentChunk(
            organization_id=version.organization_id,
            document_id=version.document_id,
            version_id=version.id,
            ordinal=chunk.ordinal,
            heading=chunk.heading,
            content=chunk.content,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
            token_estimate=chunk.token_estimate,
        )
        for chunk in chunks
    )
    db.flush()
    return len(chunks)
