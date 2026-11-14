import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BackgroundJob(Base):
    """Work that runs outside the API request, in the worker.

    The API enqueues jobs for organizations it manages; the worker, running
    as eka_worker, claims and finishes them (migration c6a2e9f4b1d7). The
    payload only names things (ids), never secrets: credentials stay in
    their own encrypted store.
    """

    __tablename__ = "background_jobs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', "
            "'cancelled')",
            name="ck_background_jobs_status",
        ),
        CheckConstraint(
            "attempts >= 0 AND max_attempts >= 1",
            name="ck_background_jobs_attempts",
        ),
        # At most one waiting or running job per organization, kind and key:
        # asking twice for the same sync does not run it twice.
        Index(
            "uq_background_jobs_active_dedupe",
            "organization_id",
            "kind",
            "dedupe_key",
            unique=True,
            postgresql_where=text(
                "status IN ('queued', 'running') AND dedupe_key IS NOT NULL"
            ),
            sqlite_where=text(
                "status IN ('queued', 'running') AND dedupe_key IS NOT NULL"
            ),
        ),
        Index("ix_background_jobs_status_run_after", "status", "run_after"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_background_jobs_organization_id_organizations",
        ),
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(String(64), nullable=False)

    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=dict,
        nullable=False,
    )

    dedupe_key: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        default="queued",
        server_default=text("'queued'"),
        nullable=False,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )

    max_attempts: Mapped[int] = mapped_column(
        Integer,
        default=5,
        server_default=text("5"),
        nullable=False,
    )

    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )

    locked_by: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_background_jobs_created_by_user_id_users",
        ),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
