import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditEvent(Base):
    """Something that changed in an organization, who did it and how.

    Rows are written only by database triggers (migration a7e3c9f1d4b2), so
    the application can neither skip nor forge an event, and nobody can
    change or remove one.
    """

    __tablename__ = "audit_events"

    __table_args__ = (
        Index(
            "ix_audit_events_organization_created",
            "organization_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="RESTRICT",
            name="fk_audit_events_organization_id_organizations",
        ),
        nullable=False,
    )

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_audit_events_actor_user_id_users",
        ),
        nullable=True,
    )

    actor_database_login: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    target_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    target_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )

    details: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        server_default=text("'{}'"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
