"""The sync engine: one way to bring any source into the archive.

Runs in the worker as the job ``connection.sync`` (one active job per
connection). For each change the connector reports:

- changed item: fetch its text, normalize it; if the hash equals the
  current version, only metadata and permissions are refreshed; otherwise
  the normalized snapshot is stored (content-addressed key) and a new
  version becomes current;
- removed item (or, on a complete listing, an item no longer listed): the
  document leaves retrieval at once;
- permissions are replaced and readers re-resolved every time.

Each item runs in its own savepoint: one broken file never stops the rest.
The connector's cursor is saved at the end, so the next run continues from
there. Phase 6 adds chunking and embeddings between "stored" and "ready".
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import (
    CONNECTORS,
    ConnectionContext,
    ConnectorAuthError,
    ConnectorError,
    SourceItem,
)
from app.core.errors import DomainError
from app.models.background_job import BackgroundJob
from app.models.data_connection import DataConnection
from app.models.document import Document
from app.services import document_service as documents
from app.services.catalog_service import INTROSPECT_JOB
from app.services.connection_scope import (
    allowed_mime_types,
    file_types_fingerprint,
)
from app.services.credential_service import load_credentials
from app.services.indexing_service import index_version
from app.services.document_permission_service import (
    replace_document_permissions,
)
from app.services.job_queue import enqueue_job, job_handler
from app.services.object_storage import ObjectStorage, get_object_storage


logger = logging.getLogger("eka.sync")

SYNC_JOB = "connection.sync"
SYNCABLE_STATUSES = ("active", "error")


class ConnectionNotSyncableError(DomainError):
    status_code = 409


def _now() -> datetime:
    return datetime.now(timezone.utc)


def snapshot_key(document: Document, hash_: str) -> str:
    # Ids and hashes only: a key never reveals a title or file name.
    return (
        f"{document.organization_id}/{document.connection_id}/"
        f"{document.id}/{hash_}/normalized.txt"
    )


def request_sync(
    db: Session,
    *,
    connection: DataConnection,
    actor_user_id: uuid.UUID,
) -> BackgroundJob:
    """API side: queue a sync, or return the one already waiting."""
    if connection.status not in SYNCABLE_STATUSES:
        raise ConnectionNotSyncableError(
            f"A {connection.status} connection is not synchronized"
        )

    # A database is never copied: its sync refreshes the catalog.
    if connection.kind == "database":
        kind, dedupe_key = INTROSPECT_JOB, f"introspect:{connection.id}"
    else:
        kind, dedupe_key = SYNC_JOB, f"sync:{connection.id}"

    return enqueue_job(
        db,
        organization_id=connection.organization_id,
        kind=kind,
        created_by_user_id=actor_user_id,
        payload={"connection_id": str(connection.id)},
        dedupe_key=dedupe_key,
    )


def _credentials(db: Session, connection: DataConnection) -> dict | None:
    try:
        return load_credentials(
            db,
            organization_id=connection.organization_id,
            connection_id=connection.id,
        )
    except DomainError:
        # No secret stored, or storage not configured here: connectors
        # that need one raise ConnectorAuthError themselves.
        return None


def _sync_item(
    db: Session,
    *,
    connection: DataConnection,
    item: SourceItem,
    text: str,
    storage: ObjectStorage,
) -> str:
    document = documents.upsert_document(
        db,
        organization_id=connection.organization_id,
        connection_id=connection.id,
        external_id=item.external_id,
        title=item.title,
        mime_type=item.mime_type,
    )

    normalized = documents.normalize_content(text)
    hash_ = documents.content_hash(normalized)
    outcome = "unchanged"

    current = documents.current_version(db, document)
    if current is None or current.content_hash != hash_:
        stored = storage.put(
            snapshot_key(document, hash_), normalized.encode("utf-8")
        )
        version = documents.add_version(
            db,
            document=document,
            content_hash=hash_,
            size_bytes=stored.size_bytes,
            mime_type=item.mime_type,
            source_revision=item.revision,
            source_modified_at=item.modified_at,
            normalized_object_key=stored.key,
        )
        documents.mark_version_ready(db, version)
        documents.activate_version(db, document=document, version=version)
        # The new version becomes searchable in the same transaction.
        index_version(db, version=version, text=normalized)
        outcome = "new_version"
    elif document.status == "removed":
        # Back at the source with the same content.
        documents.activate_version(db, document=document, version=current)
        outcome = "restored"

    replace_document_permissions(
        db, document=document, permissions=list(item.permissions)
    )
    document.last_synced_at = _now()
    db.flush()
    return outcome


def _same_revision(
    db: Session,
    connection: DataConnection,
    item: SourceItem,
) -> Document | None:
    """The document, when the source says this item has not changed.

    Then nothing is downloaded or parsed again.
    """
    if not item.revision:
        return None
    document = db.scalars(
        select(Document).where(
            Document.connection_id == connection.id,
            Document.external_id == item.external_id,
        )
    ).one_or_none()
    if document is None:
        return None
    current = documents.current_version(db, document)
    if current is None or current.source_revision != item.revision:
        return None
    return document


def _refresh_item(db: Session, *, document: Document, item: SourceItem) -> str:
    outcome = "unchanged"
    if document.status == "removed":
        current = documents.current_version(db, document)
        documents.activate_version(db, document=document, version=current)
        outcome = "restored"
    if document.title != item.title:
        document.title = item.title
    replace_document_permissions(
        db, document=document, permissions=list(item.permissions)
    )
    document.last_synced_at = _now()
    db.flush()
    return outcome


def _source_cursor(connection: DataConnection) -> str | None:
    """The connector's cursor, or None for a full listing.

    With a file-type filter, the cursor is saved with the filter's
    fingerprint: when an admin changes the filter, the next sync lists
    everything again, so newly allowed files come in and newly
    excluded ones leave.
    """
    cursor = connection.sync_cursor
    fingerprint = file_types_fingerprint(connection.settings)
    if fingerprint is None:
        if cursor is not None and cursor.startswith("scope:"):
            return None
        return cursor
    prefix = f"scope:{fingerprint}:"
    if cursor is None or not cursor.startswith(prefix):
        return None
    return cursor[len(prefix):] or None


def _saved_cursor(connection: DataConnection, cursor: str | None) -> str | None:
    fingerprint = file_types_fingerprint(connection.settings)
    if fingerprint is None:
        return cursor
    return f"scope:{fingerprint}:{cursor or ''}"


def _remove(db: Session, connection: DataConnection, external_ids) -> int:
    if not external_ids:
        return 0
    removed = 0
    for document in db.scalars(
        select(Document).where(
            Document.connection_id == connection.id,
            Document.external_id.in_(list(external_ids)),
            Document.status != "removed",
        )
    ):
        documents.remove_document(db, document=document)
        removed += 1
    return removed


def sync_connection(
    db: Session,
    *,
    connection_id: uuid.UUID,
    storage: ObjectStorage | None = None,
) -> dict[str, int]:
    summary = {
        "new_version": 0,
        "unchanged": 0,
        "restored": 0,
        "removed": 0,
        "failed": 0,
    }

    connection = db.get(DataConnection, connection_id)
    if connection is None or connection.status not in SYNCABLE_STATUSES:
        # Paused, disconnected or gone since the job was queued.
        return summary

    factory = CONNECTORS.get(connection.provider)
    if factory is None:
        raise LookupError(f"No connector for provider {connection.provider}")

    storage = storage or get_object_storage()
    connector = factory(
        ConnectionContext(
            organization_id=connection.organization_id,
            connection_id=connection.id,
            provider=connection.provider,
            settings=dict(connection.settings),
            credentials=_credentials(db, connection),
            db=db,
            storage=storage,
        )
    )

    try:
        return _run(
            db,
            connection=connection,
            connector=connector,
            storage=storage,
            summary=summary,
        )
    finally:
        # Connectors that hold a network client release it here.
        close = getattr(connector, "close", None)
        if callable(close):
            close()


def _run(
    db: Session,
    *,
    connection: DataConnection,
    connector,
    storage: ObjectStorage,
    summary: dict[str, int],
) -> dict[str, int]:
    def refused(exc: ConnectorAuthError) -> dict[str, int]:
        # Retrying will not help: the connection needs an admin. What was
        # already synchronized in this run is kept.
        connection.status = "error"
        connection.last_error = f"Authentication failed: {exc}"[:500]
        db.flush()
        return summary

    try:
        changes = connector.list_changes(_source_cursor(connection))
    except ConnectorAuthError as exc:
        return refused(exc)

    seen: set[str] = set()
    errors: list[str] = []
    # The source failed (not one file): stop, keep the old cursor, and
    # let the job retry. Items already done are skipped next time by
    # their revision.
    interrupted = False

    # The admin's file-type filter: excluded files are not read, and
    # leave retrieval if they were in.
    allowed = allowed_mime_types(connection.settings)
    excluded = []

    for item in changes.changed:
        if allowed is not None and item.mime_type not in allowed:
            excluded.append(item.external_id)
            continue
        seen.add(item.external_id)
        try:
            known = _same_revision(db, connection, item)
            if known is not None:
                with db.begin_nested():
                    outcome = _refresh_item(db, document=known, item=item)
                summary[outcome] += 1
                continue

            text = connector.fetch_text(item)
            with db.begin_nested():
                outcome = _sync_item(
                    db,
                    connection=connection,
                    item=item,
                    text=text,
                    storage=storage,
                )
            summary[outcome] += 1
        except ConnectorAuthError as exc:
            return refused(exc)
        except ConnectorError as exc:
            summary["failed"] += 1
            errors.append(f"{item.external_id}: {type(exc).__name__}")
            logger.warning("sync %s: source failed: %s", connection.id, exc)
            interrupted = True
            break
        except Exception as exc:
            summary["failed"] += 1
            errors.append(f"{item.external_id}: {type(exc).__name__}")
            logger.warning(
                "sync %s: item %s failed: %s",
                connection.id,
                item.external_id,
                exc,
            )

    summary["removed"] += _remove(
        db, connection, [*changes.removed, *excluded]
    )

    # A complete listing removes what it did not see; an interrupted one
    # did not see everything, so it removes nothing.
    if changes.complete and not interrupted:
        missing = db.scalars(
            select(Document.external_id).where(
                Document.connection_id == connection.id,
                Document.status != "removed",
            )
        ).all()
        summary["removed"] += _remove(
            db, connection, [e for e in missing if e not in seen]
        )

    if not interrupted:
        connection.sync_cursor = _saved_cursor(connection, changes.cursor)
    connection.last_synced_at = _now()
    connection.status = "active"
    connection.last_error = (
        f"{len(errors)} item(s) failed: " + ", ".join(errors[:5])
    )[:500] if errors else None
    db.flush()

    logger.info("sync %s: %s", connection.id, summary)
    return summary


@job_handler(SYNC_JOB)
def run_sync_job(db: Session, job: BackgroundJob) -> None:
    sync_connection(db, connection_id=uuid.UUID(job.payload["connection_id"]))
