

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.membership import OrganizationMembership
    from app.models.user import User


class Organization(Base):
    __tablename__ = "organizations"

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'pending_deletion', 'deleted')",
            name="ck_organization_status",
        ),
        CheckConstraint(
            "history_retention_days IN (0, 30, 90, 365)",
            name="ck_organizations_history_retention_days",
        ),
        CheckConstraint(
            "agent_max_steps BETWEEN 1 AND 8",
            name="ck_organizations_agent_max_steps",
        ),
        CheckConstraint(
            "agent_max_tool_calls BETWEEN 1 AND 12",
            name="ck_organizations_agent_max_tool_calls",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_organizations_created_by_user_id_users",
        ),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Changed only by the platform (see migration f5c1a8d3e6b9). An
    # organization that is not active is read-only in the application.
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        server_default=text("'active'"),
        nullable=False,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # How long each person's questions are kept, in days; 0 keeps none
    # (migration e6b1d4a8c2f9).
    history_retention_days: Mapped[int] = mapped_column(
        Integer,
        default=90,
        server_default=text("90"),
        nullable=False,
    )

    # Limits of the agent for one answer (migration b8e4d2f6a1c3): model
    # calls and tool calls.
    agent_max_steps: Mapped[int] = mapped_column(
        Integer,
        default=4,
        server_default=text("4"),
        nullable=False,
    )
    agent_max_tool_calls: Mapped[int] = mapped_column(
        Integer,
        default=6,
        server_default=text("6"),
        nullable=False,
    )

    creator: Mapped["User | None"] = relationship(
        back_populates="organizations_created",
        foreign_keys=[created_by_user_id],
    )

    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Organization(name={self.name!r})>"
