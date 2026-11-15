"""Receive a member's file and hand it to the sync engine.

The API only checks and stores: the size, the real type (from the bytes),
the hash. Reading the text happens in the worker, through the file_upload
connector, so a heavy or hostile file never slows down a request.
"""

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import (
    DomainError,
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
)
from app.models.data_connection import DataConnection
from app.models.file_upload import FileUpload
from app.services.connection_scope import allowed_mime_types
from app.services.object_storage import ObjectStorage, get_object_storage
from app.services.sync_service import request_sync
from app.services.text_extraction import (
    MAX_FILE_BYTES,
    ExtractionError,
    detect_type,
)


class UploadTooLargeError(DomainError):
    status_code = 413


class UnsupportedUploadError(DomainError):
    status_code = 415


class NotAnUploadConnectionError(InvalidInputError):
    pass


class UploadNotFoundError(NotFoundError):
    pass


def _clean_filename(filename: str | None) -> str:
    name = (filename or "").replace("\\", "/").split("/")[-1].strip()
    name = "".join(ch for ch in name if ch.isprintable())
    return (name or "upload")[:255]


def create_upload(
    db: Session,
    *,
    connection: DataConnection,
    user_id: uuid.UUID,
    user_email: str,
    filename: str | None,
    data: bytes,
    visibility: str,
    storage: ObjectStorage | None = None,
    uploader_role: str | None = None,
) -> FileUpload:
    if connection.provider != "file_upload":
        raise NotAnUploadConnectionError(
            "Files can only be uploaded to a file upload connection"
        )
    roles = (connection.settings.get("scope") or {}).get("roles")
    if uploader_role is not None and roles and uploader_role not in roles:
        # The file would be invisible to the person who uploaded it.
        raise ForbiddenError("Your role does not use this connection")
    if visibility not in ("organization", "private"):
        raise InvalidInputError("visibility must be organization or private")
    if len(data) > MAX_FILE_BYTES:
        raise UploadTooLargeError("The file is larger than 20 MB")
    if not data:
        raise UnsupportedUploadError("The file is empty")

    try:
        mime_type = detect_type(data)
    except ExtractionError as exc:
        raise UnsupportedUploadError(str(exc).capitalize()) from None
    allowed = allowed_mime_types(connection.settings)
    if allowed is not None and mime_type not in allowed:
        raise UnsupportedUploadError(
            "This connection does not accept this type of file"
        )

    upload_id = uuid.uuid4()
    # Ids only: the key reveals nothing about the file.
    key = (
        f"{connection.organization_id}/{connection.id}/uploads/"
        f"{upload_id}/original"
    )
    stored = (storage or get_object_storage()).put(key, data)

    upload = FileUpload(
        id=upload_id,
        organization_id=connection.organization_id,
        connection_id=connection.id,
        uploaded_by=user_id,
        uploader_email=user_email,
        filename=_clean_filename(filename),
        mime_type=mime_type,
        size_bytes=stored.size_bytes,
        sha256=hashlib.sha256(data).hexdigest(),
        original_object_key=stored.key,
        visibility=visibility,
        status="active",
    )
    db.add(upload)
    db.flush()

    request_sync(db, connection=connection, actor_user_id=user_id)
    return upload


def list_my_uploads(
    db: Session,
    *,
    connection_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[FileUpload]:
    return list(
        db.scalars(
            select(FileUpload)
            .where(
                FileUpload.connection_id == connection_id,
                FileUpload.uploaded_by == user_id,
                FileUpload.status == "active",
            )
            .order_by(FileUpload.created_at.desc())
        )
    )


def delete_upload(
    db: Session,
    *,
    connection: DataConnection,
    upload_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    upload = db.scalars(
        select(FileUpload).where(
            FileUpload.id == upload_id,
            FileUpload.connection_id == connection.id,
            FileUpload.uploaded_by == user_id,
            FileUpload.status == "active",
        )
    ).one_or_none()
    if upload is None:
        raise UploadNotFoundError("Upload not found")

    from datetime import datetime, timezone

    upload.status = "deleted"
    upload.deleted_at = datetime.now(timezone.utc)
    db.flush()

    # The next sync takes the document out of retrieval.
    request_sync(db, connection=connection, actor_user_id=user_id)
