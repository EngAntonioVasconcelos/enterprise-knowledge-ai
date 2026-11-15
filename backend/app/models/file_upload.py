import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
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
    visibility (migration d4a1e7b3c8f2).
    """

    __tablename__ = "file_uploads"

    __table_args__ = (
        CheckConstraint(
            "visibility IN ('organization', 'private')",
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
