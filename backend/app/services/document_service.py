"""The document archive: identities, immutable versions, activation.

Used by ingestion in the worker (ADR-003):

1. ``upsert_document`` finds or creates the document for a source item.
2. ``add_version`` records new content, unless it is the same as the
   current version (same hash of the normalized text): nothing to redo.
3. Processing (chunks, embeddings) happens while the version is
   ``processing``; then ``mark_version_ready`` or ``fail_version``.
4. ``activate_version`` makes a ready version current. Until then, the
   previous version stays current, so a failure never empties a document.
5. ``remove_document`` takes a document out of retrieval at once.
"""

import hashlib
import re
import unicodedata
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models.document import Document, DocumentVersion


class DocumentVersionError(ConflictError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_content(text: str) -> str:
    """Deterministic form of extracted text (ADR-003, 4.1).

    Same meaning, same bytes: Unicode NFC, one kind of line break, no
    trailing spaces, at most one empty line in a row, no leading or
    trailing blank lines. Anything else (wording, order, numbers) is a
    real change.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip("\n")


def content_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def upsert_document(
    db: Session,
    *,
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    external_id: str,
    title: str,
    mime_type: str | None = None,
    uploaded_by: uuid.UUID | None = None,
) -> Document:
    document = db.scalars(
        select(Document).where(
            Document.connection_id == connection_id,
            Document.external_id == external_id,
        )
    ).one_or_none()

    if document is None:
        document = Document(
            organization_id=organization_id,
            connection_id=connection_id,
            external_id=external_id,
            title=title,
            mime_type=mime_type,
            uploaded_by=uploaded_by,
            status="pending",
        )
        db.add(document)
        db.flush()
        return document

    if document.title != title:
        document.title = title
    if mime_type and document.mime_type != mime_type:
        document.mime_type = mime_type
    db.flush()
    return document


def current_version(
    db: Session,
    document: Document,
) -> DocumentVersion | None:
    if document.current_version_id is None:
        return None
    return db.get(DocumentVersion, document.current_version_id)


def add_version(
    db: Session,
    *,
    document: Document,
    content_hash: str,
    size_bytes: int | None = None,
    mime_type: str | None = None,
    source_revision: str | None = None,
    source_modified_at: datetime | None = None,
    original_object_key: str | None = None,
    normalized_object_key: str | None = None,
) -> DocumentVersion | None:
    """Record new content; None when it equals the current version."""
    current = current_version(db, document)
    if current is not None and current.content_hash == content_hash:
        return None

    # The database assigns the number; this value only matters where no
    # trigger runs (unit tests on SQLite) and follows the same rule.
    last = db.scalar(
        select(func.max(DocumentVersion.version_number)).where(
            DocumentVersion.document_id == document.id
        )
    )

    version = DocumentVersion(
        document_id=document.id,
        organization_id=document.organization_id,
        version_number=(last or 0) + 1,
        content_hash=content_hash,
        size_bytes=size_bytes,
        mime_type=mime_type,
        source_revision=source_revision,
        source_modified_at=source_modified_at,
        original_object_key=original_object_key,
        normalized_object_key=normalized_object_key,
        status="processing",
    )
    db.add(version)
    db.flush()
    db.refresh(version)
    return version


def _require_processing(version: DocumentVersion) -> None:
    if version.status != "processing":
        raise DocumentVersionError(
            "A processed document version cannot change"
        )


def mark_version_ready(db: Session, version: DocumentVersion) -> None:
    _require_processing(version)
    version.status = "ready"
    version.ready_at = _now()
    db.flush()


def fail_version(db: Session, version: DocumentVersion, *, error: str) -> None:
    _require_processing(version)
    version.status = "failed"
    version.error = error[:500]
    db.flush()

    document = db.get(Document, version.document_id)
    if document.current_version_id is None:
        # Nothing valid to show yet; with a previous version it stays.
        document.status = "failed"
        db.flush()


def activate_version(
    db: Session,
    *,
    document: Document,
    version: DocumentVersion,
) -> None:
    if version.document_id != document.id or version.status != "ready":
        raise DocumentVersionError(
            "The current version must be a ready version of the same "
            "document"
        )

    now = _now()
    document.current_version_id = version.id
    document.status = "active"
    document.last_synced_at = now
    document.removed_at = None
    document.updated_at = now
    db.flush()


def remove_document(db: Session, *, document: Document) -> None:
    """Take a document out of retrieval; its versions stay (retention)."""
    now = _now()
    document.status = "removed"
    document.removed_at = now
    document.updated_at = now
    db.flush()
