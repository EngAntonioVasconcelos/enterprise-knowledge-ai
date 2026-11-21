import uuid
from datetime import date

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnswerEvent(Base):
    """One answer, for the organization dashboard: no person, no text.

    Owners and admins read these rows (migration f2c7a9e4b6d1); the JSON
    shape check is PostgreSQL-only and lives in the migration.
    """

    __tablename__ = "answer_events"

    __table_args__ = (
        CheckConstraint(
            "language IN ('pt', 'en', 'fr')",
            name="ck_answer_events_language",
        ),
        CheckConstraint(
            "gap_reason IS NULL OR (abstained AND gap_reason IN "
            "('no_sources', 'not_found', 'checks', 'not_relevant'))",
            name="ck_answer_events_gap_reason",
        ),
        Index(
            "ix_answer_events_organization_day",
            "organization_id",
            "answered_on",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_answer_events_organization_id_organizations",
        ),
        nullable=False,
    )

    # Set by the database (its own date), never by the application.
    answered_on: Mapped[date] = mapped_column(
        Date, server_default=text("CURRENT_DATE"), nullable=False
    )
    abstained: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)

    cited_document_ids: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=list,
        nullable=False,
    )
    # AL-3, only when there was no safe answer: the documents given to the
    # model (ids only) and why there was no answer. Older rows have none.
    consulted_document_ids: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=list,
        nullable=False,
    )
    gap_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
