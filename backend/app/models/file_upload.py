import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    PrimaryKeyConstraint,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FileUpload(Base):
    """A file a member uploaded to a ``file_upload`` connection.

    The original is in object storage; the sync engine reads it through the
    file_upload connector like any other source. Only the uploader sees the
    record (its file name can be telling); the document follows the chosen
    visibility (migration d4a1e7b3c8f2): the whole organization, only the
    uploader, or the uploader and chosen people (``people``, AL-8b).
    """

    __tablename__ = "file_uploads"

    __table_args__ = (
        CheckConstraint(
            "visibility IN ('organization', 'private', 'people')",
            name="ck_file_uploads_visibility",
        ),
        CheckConstraint(
            "status IN ('active', 'deleted')",
            name="ck_file_uploads_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_file_uploads_organization_id_organizations",
        ),
        nullable=False,
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "data_connections.id",
            ondelete="CASCADE",
            name="fk_file_uploads_connection_id_data_connections",
        ),
        nullable=False,
    )

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_file_uploads_uploaded_by_users",
        ),
        nullable=True,
    )

    # Kept so the worker can grant "only me" without reading users.
    uploader_email: Mapped[str] = mapped_column(String(320), nullable=False)

    filename: Mapped[str] = mapped_column(String(255), nullable=False)

    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)

    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    original_object_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    visibility: Mapped[str] = mapped_column(String(16), nullable=False)

    status: Mapped[str] = mapped_column(
        String(16),
        default="active",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class FileUploadReader(Base):
    """A person the uploader chose to read a ``people`` upload (AL-8b).

    Written only by app_private.add_upload_readers, which checks that the
    caller uploaded the file and that each reader is an active member of
    its organization, and keeps the reader's e-mail so the worker grants
    access without reading users. Only the worker reads these rows.
    """

    __tablename__ = "file_upload_readers"

    __table_args__ = (
        PrimaryKeyConstraint("upload_id", "user_id", name="pk_file_upload_readers"),
    )

    upload_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "file_uploads.id",
            ondelete="CASCADE",
            name="fk_file_upload_readers_upload_id_file_uploads",
        ),
        nullable=False,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_file_upload_readers_organization_id_organizations",
        ),
        nullable=False,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_file_upload_readers_user_id_users",
        ),
        nullable=False,
    )

    reader_email: Mapped[str] = mapped_column(String(320), nullable=False)
