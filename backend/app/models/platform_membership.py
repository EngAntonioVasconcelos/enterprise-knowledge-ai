import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class PlatformMembership(Base):
    __tablename__ = "platform_memberships"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "role",
            name="uq_platform_membership_user_role",
        ),
        CheckConstraint(
            "role = 'platform_admin'",
            name="ck_platform_membership_role",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_platform_memberships_user_id_users",
        ),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(50),
        default="platform_admin",
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="platform_memberships",
        passive_deletes="all",
    )

    def __repr__(self) -> str:
        return (
            f"<PlatformMembership("
            f"user_id={self.user_id}, "
            f"role={self.role!r}, "
            f"is_active={self.is_active})>"
        )
