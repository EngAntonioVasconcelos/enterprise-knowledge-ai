

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
    validates,
)

from app.models.authentication_identity import AuthenticationIdentity

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.membership import OrganizationMembership
    from app.models.organization import Organization
    from app.models.platform_membership import PlatformMembership


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint(
            "email",
            name="uq_user_email",
        ),
        CheckConstraint(
            "email = lower(email)",
            name="ck_user_email_lowercase",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
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

    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    organizations_created: Mapped[list["Organization"]] = relationship(
        back_populates="creator",
        foreign_keys="Organization.created_by_user_id",
    )

    authentication_identities: Mapped[list["AuthenticationIdentity"]] = relationship(
    back_populates="user",
    cascade="all, delete-orphan",
)
    platform_memberships: Mapped[list["PlatformMembership"]] = relationship(
        back_populates="user",
        passive_deletes="all",
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="uploaded_by_user",
        foreign_keys="Document.uploaded_by",
    )
    @validates("email")
    def normalize_email(self, key: str, value: str) -> str:
        return value.strip().lower()
    def __repr__(self) -> str:
        return f"<User(email={self.email!r})>"

