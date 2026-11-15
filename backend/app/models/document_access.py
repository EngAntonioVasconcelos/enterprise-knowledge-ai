import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


PRINCIPAL_TYPES = ("user", "group", "domain", "anyone", "organization")
PERMISSION_ROLES = ("reader", "commenter", "writer", "owner")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentPermission(Base):
    """Who may open a document, as the source says (raw ACL).

    Written by the worker at each synchronization. ``principal`` is a
    lower-case e-mail (user, group), a domain, or empty (anyone,
    organization). It decides nothing by itself: document_access holds the
    resolved readers (migration a2d7c4e9f1b6).
    """

    __tablename__ = "document_permissions"

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "principal_type",
            "principal",
            name="uq_document_permissions_principal",
        ),
        CheckConstraint(
            "principal_type IN ('user', 'group', 'domain', 'anyone', "
            "'organization')",
            name="ck_document_permissions_principal_type",
        ),
        CheckConstraint(
            "role IN ('reader', 'commenter', 'writer', 'owner')",
            name="ck_document_permissions_role",
        ),
        Index(
            "ix_document_permissions_lookup",
            "organization_id",
            "principal_type",
            "principal",
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
            name="fk_document_permissions_document_id_documents",
        ),
        nullable=False,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_document_permissions_organization_id_organizations",
        ),
        nullable=False,
    )

    principal_type: Mapped[str] = mapped_column(String(16), nullable=False)

    principal: Mapped[str] = mapped_column(String(320), nullable=False)

    role: Mapped[str] = mapped_column(String(16), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )


class DocumentAccess(Base):
    """A platform user who may read a document: the resolved ACL.

    Only database functions write it, from document_permissions and the
    organization's active members. Every read of documents, versions and,
    later, indexed passages is filtered through it.
    """

    __tablename__ = "document_access"

    __table_args__ = (
        Index(
            "ix_document_access_user_organization",
            "user_id",
            "organization_id",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
            name="fk_document_access_document_id_documents",
        ),
        primary_key=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_document_access_user_id_users",
        ),
        primary_key=True,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_document_access_organization_id_organizations",
        ),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )
