import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


DOCUMENT_STATUSES = ("pending", "active", "failed", "removed")
VERSION_STATUSES = ("processing", "ready", "failed")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    """The stable identity of a document from a source (ADR-003).

    Its content lives in immutable versions. Only a version that finished
    processing can become current, so retrieval never sees half-indexed
    content (migration f3a8c6e1b9d4).
    """

    __tablename__ = "documents"

    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_id",
            name="uq_documents_connection_external_id",
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'failed', 'removed')",
            name="ck_documents_status",
        ),
        CheckConstraint(
            "status <> 'active' OR current_version_id IS NOT NULL",
            name="ck_documents_active_has_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "data_connections.id",
            ondelete="CASCADE",
            name="fk_documents_connection_id_data_connections",
        ),
        nullable=False,
    )

    # The document's id in its source (a Drive file id, an upload id).
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
    )

    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "document_versions.id",
            ondelete="RESTRICT",
            name="fk_documents_current_version_id_document_versions",
            use_alter=True,
        ),
        nullable=True,
    )

    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
        nullable=False,
    )

    organization: Mapped["Organization"] = relationship(
        back_populates="documents",
    )

    uploaded_by_user: Mapped["User | None"] = relationship(
        back_populates="documents",
        foreign_keys=[uploaded_by],
    )

    def __repr__(self) -> str:
        return f"<Document(title={self.title!r})>"


class DocumentVersion(Base):
    """One immutable snapshot of a document's content (ADR-003, ADR-004).

    The bytes live in object storage; the version keeps their keys, size
    and the SHA-256 of the normalized content, which detects real changes.
    The database numbers versions itself.
    """

    __tablename__ = "document_versions"

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_versions_number",
        ),
        CheckConstraint(
            "status IN ('processing', 'ready', 'failed')",
            name="ck_document_versions_status",
        ),
        CheckConstraint(
            "(status = 'ready') = (ready_at IS NOT NULL)",
            name="ck_document_versions_ready_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
            name="fk_document_versions_document_id_documents",
        ),
        nullable=False,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_document_versions_organization_id_organizations",
        ),
        nullable=False,
    )

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    source_revision: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    source_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    original_object_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    normalized_object_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        default="processing",
        nullable=False,
    )

    error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )

    ready_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
