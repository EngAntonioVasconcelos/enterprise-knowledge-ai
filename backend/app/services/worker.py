"""One pass of the background worker.

Each pass uses short transactions: one to claim jobs, then one per job that
runs its handler and marks it succeeded. If the handler fails, that
transaction is rolled back (nothing the handler wrote is kept) and a new one
records the failure and schedules the retry.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.context import set_worker_context
from app.models.background_job import BackgroundJob
# Job handlers and connectors register themselves when imported.
import app.connectors.file_upload  # noqa: F401
import app.services.sync_service  # noqa: F401
from app.services.job_queue import (
    UnknownJobKindError,
    claim_jobs,
    complete_job,
    fail_job,
    requeue_lost_jobs,
    run_job,
)


WORKER_ROLE = "eka_worker"


def _session(engine: Engine, assume_role: str | None) -> Session:
    db = Session(engine)
    if assume_role:
        # Whatever the login can do, this transaction can only do what the
        # worker role allows.
        db.execute(text(f"SET LOCAL ROLE {assume_role}"))
    return db


def run_once(
    engine: Engine,
    *,
    worker_id: str,
    limit: int = 1,
    assume_role: str | None = WORKER_ROLE,
) -> dict[str, int]:
    outcome = {"requeued": 0, "succeeded": 0, "retrying": 0, "failed": 0}

    with _session(engine, assume_role) as db:
        outcome["requeued"] = requeue_lost_jobs(db)
        claimed: list[uuid.UUID] = [
            job.id for job in claim_jobs(db, worker_id=worker_id, limit=limit)
        ]
        db.commit()

    for job_id in claimed:
        error: Exception | None = None

        with _session(engine, assume_role) as db:
            job = db.get(BackgroundJob, job_id)
            # Rows the handler touches are scoped to the job's organization.
            set_worker_context(db, organization_id=job.organization_id)
            try:
                run_job(db, job)
                complete_job(db, job)
                db.commit()
                outcome["succeeded"] += 1
            except Exception as exc:
                db.rollback()
                error = exc

        if error is None:
            continue

        with _session(engine, assume_role) as db:
            job = db.get(BackgroundJob, job_id)
            fail_job(
                db,
                job,
                error=f"{type(error).__name__}: {error}",
                permanent=isinstance(error, UnknownJobKindError),
            )
            final_status = job.status
            db.commit()

        outcome["failed" if final_status == "failed" else "retrying"] += 1

    return outcome
