import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrganizationOwnerRecoveryEvent(Base):
    __tablename__ = "organization_owner_recovery_events"

    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name="pk_organization_owner_recovery_events",
        ),
        ForeignKeyConstraint(
            ["organization_id", "membership_id", "recovered_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.id",
                "organization_memberships.user_id",
            ],
            name="fk_owner_recovery_event_membership_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_owner_recovery_event_actor_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "event_type = 'owner_recovered'",
            name="ck_owner_recovery_event_type",
        ),
        Index(
            "ix_owner_recovery_events_organization_created",
            "organization_id",
            "created_at",
        ),
        Index(
            "ix_owner_recovery_events_actor_user",
            "actor_user_id",
        ),
        Index(
            "ix_owner_recovery_events_recovered_user",
            "recovered_user_id",
        ),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )

    membership_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )

    recovered_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )

    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )

    actor_auth_issuer: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )

    actor_auth_subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default=text("'owner_recovered'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
