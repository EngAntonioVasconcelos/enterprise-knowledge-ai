import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class QuestionHistory(Base):
    """A question a person asked, with the answer they got.

    Only that person reads it (migration e6b1d4a8c2f9). The sources are kept
    as shown, and checked again when the entry is opened: an answer whose
    cited documents the person can no longer open is not shown.
    """

    __tablename__ = "question_history"

    # The length and JSON shape checks are PostgreSQL-only and live in the
    # migration.
    __table_args__ = (
        CheckConstraint(
            "language IN ('pt', 'en', 'fr')",
            name="ck_question_history_language",
        ),
        Index(
            "ix_question_history_owner_created",
            "organization_id",
            "user_id",
            "created_at",
        ),
        Index("ix_question_history_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_question_history_organization_id_organizations",
        ),
        nullable=False,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_question_history_user_id_users",
        ),
        nullable=False,
    )

    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    abstained: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)

    sources: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=list,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )
