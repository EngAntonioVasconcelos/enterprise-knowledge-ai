import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


CONNECTION_KINDS = ("documents", "tabular", "database", "application")
CONNECTION_STATUSES = ("active", "paused", "error", "disconnected")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DataConnection(Base):
    """A source of data an organization has connected (ADR-006).

    Only what is not secret lives here: credentials are kept apart,
    encrypted, in their own table. A connection is never deleted; it ends
    as "disconnected", which is final (migration d8b4f1a7c3e5).
    """

    __tablename__ = "data_connections"

    __table_args__ = (
        CheckConstraint(
            "kind IN ('documents', 'tabular', 'database', 'application')",
            name="ck_data_connections_kind",
        ),
        CheckConstraint(
            "status IN ('active', 'paused', 'error', 'disconnected')",
            name="ck_data_connections_status",
        ),
        CheckConstraint(
            "(status = 'disconnected') = (disconnected_at IS NOT NULL)",
            name="ck_data_connections_disconnected_at",
        ),
        # Names are unique among the connections still in use.
        Index(
            "uq_data_connections_active_name",
            "organization_id",
            "name",
            unique=True,
            postgresql_where=text("status <> 'disconnected'"),
            sqlite_where=text("status <> 'disconnected'"),
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
            name="fk_data_connections_organization_id_organizations",
        ),
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(String(16), nullable=False)

    provider: Mapped[str] = mapped_column(String(64), nullable=False)

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    status: Mapped[str] = mapped_column(
        String(16),
        default="active",
        server_default=text("'active'"),
        nullable=False,
    )

    settings: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=dict,
        nullable=False,
    )

    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # The connector's position in the source's change feed; only the
    # worker moves it (migration c9f4b2a8e6d1).
    sync_cursor: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_data_connections_created_by_user_id_users",
        ),
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
        nullable=False,
    )

    disconnected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
