"""The background job queue.

The API enqueues a job in the transaction of the change that needs it. The
worker (app/services/worker.py) claims jobs with SKIP LOCKED, so several
workers never run the same job, then runs each one and records the outcome.

A job's handler and its completion commit together: either the work and the
"succeeded" status are both saved, or neither is and the job is retried.
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.background_job import BackgroundJob


# A running job whose worker has not finished it within this time is
# assumed lost (the worker stopped) and goes back to the queue.
LEASE = timedelta(minutes=15)
MAX_BACKOFF = timedelta(hours=1)

JobHandler = Callable[[Session, BackgroundJob], None]

_HANDLERS: dict[str, JobHandler] = {}


class UnknownJobKindError(LookupError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    # SQLite, used by unit tests, returns naive datetimes.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def job_handler(kind: str) -> Callable[[JobHandler], JobHandler]:
    """Register the function that runs jobs of this kind."""

    def register(handler: JobHandler) -> JobHandler:
        if kind in _HANDLERS:
            raise ValueError(f"A handler for {kind} already exists")
        _HANDLERS[kind] = handler
        return handler

    return register


def unregister_job_handler(kind: str) -> None:
    _HANDLERS.pop(kind, None)


def enqueue_job(
    db: Session,
    *,
    organization_id: uuid.UUID,
    kind: str,
    created_by_user_id: uuid.UUID,
    payload: dict | None = None,
    dedupe_key: str | None = None,
    run_after: datetime | None = None,
) -> BackgroundJob:
    """Add a job, or return the one already waiting with the same key."""
    job = BackgroundJob(
        organization_id=organization_id,
        kind=kind,
        payload=payload or {},
        dedupe_key=dedupe_key,
        created_by_user_id=created_by_user_id,
        run_after=run_after or _now(),
    )

    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        if dedupe_key is None:
            raise
        existing = db.scalars(
            select(BackgroundJob).where(
                BackgroundJob.organization_id == organization_id,
                BackgroundJob.kind == kind,
                BackgroundJob.dedupe_key == dedupe_key,
                BackgroundJob.status.in_(("queued", "running")),
            )
        ).one_or_none()
        if existing is None:
            raise
        return existing

    return job


def retry_delay(attempts: int) -> timedelta:
    """30 s, 1 min, 2 min, 4 min... at most an hour."""
    return min(timedelta(seconds=30 * 2 ** max(attempts - 1, 0)), MAX_BACKOFF)


def requeue_lost_jobs(db: Session, *, now: datetime | None = None) -> int:
    now = now or _now()
    lost = db.scalars(
        select(BackgroundJob)
        .where(
            BackgroundJob.status == "running",
            BackgroundJob.locked_at < now - LEASE,
        )
        .with_for_update(skip_locked=True)
    ).all()

    for job in lost:
        job.locked_by = None
        job.locked_at = None
        job.last_error = "lease expired: the worker did not finish the job"
        # A job that keeps taking its worker down must not loop forever.
        if job.attempts >= job.max_attempts:
            job.status = "failed"
            job.finished_at = now
        else:
            job.status = "queued"

    db.flush()
    return len(lost)


def claim_jobs(
    db: Session,
    *,
    worker_id: str,
    limit: int = 1,
    now: datetime | None = None,
) -> list[BackgroundJob]:
    now = now or _now()
    jobs = db.scalars(
        select(BackgroundJob)
        .where(
            BackgroundJob.status == "queued",
            BackgroundJob.run_after <= now,
        )
        .order_by(BackgroundJob.run_after, BackgroundJob.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()

    for job in jobs:
        job.status = "running"
        job.attempts += 1
        job.locked_by = worker_id
        job.locked_at = now

    db.flush()
    return list(jobs)


def run_job(db: Session, job: BackgroundJob) -> None:
    handler = _HANDLERS.get(job.kind)
    if handler is None:
        raise UnknownJobKindError(f"No handler for job kind {job.kind}")
    handler(db, job)


def complete_job(
    db: Session,
    job: BackgroundJob,
    *,
    now: datetime | None = None,
) -> None:
    job.status = "succeeded"
    job.finished_at = now or _now()
    job.last_error = None
    db.flush()


def fail_job(
    db: Session,
    job: BackgroundJob,
    *,
    error: str,
    permanent: bool = False,
    now: datetime | None = None,
) -> None:
    now = now or _now()
    job.last_error = error[:500]
    job.locked_by = None
    job.locked_at = None

    if permanent or job.attempts >= job.max_attempts:
        job.status = "failed"
        job.finished_at = now
    else:
        job.status = "queued"
        job.run_after = now + retry_delay(job.attempts)

    db.flush()
