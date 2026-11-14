import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.db.context import set_organization_context
from app.models import BackgroundJob
from app.services.job_queue import claim_jobs, complete_job, enqueue_job
from app.services.worker import WORKER_ROLE, _session
from scripts.prepare_test_database import TEST_ADMIN_URL
from tests.integration.test_postgres_rls import (
    _authenticate,
    _create_organization,
    _create_user,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def jobs_db(postgres_engine):
    # One administrator connection that plays the API (SET ROLE eka_runtime)
    # and the worker (SET ROLE eka_worker) on the same uncommitted data.
    engine = create_engine(TEST_ADMIN_URL)
    connection = engine.connect()
    transaction = connection.begin()
    db = sessionmaker(
        bind=connection,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )()

    try:
        db.execute(text("SET ROLE eka_runtime"))
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def _as(db, role):
    db.flush()
    db.execute(text(f"SET ROLE {role}"))


def _refused(db, statement, fragment):
    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            db.execute(statement)
    assert fragment in str(error.value.orig)


def _owner_and_organization(db):
    owner = _create_user(db, "jobs-owner")
    organization = _create_organization(db, owner)
    _authenticate(db, owner)
    set_organization_context(db, organization_id=organization.id)
    return owner, organization


def _enqueue(db, owner, organization, **values):
    job = enqueue_job(
        db,
        organization_id=organization.id,
        kind="test.echo",
        created_by_user_id=owner.id,
        **values,
    )
    db.flush()
    return job.id


def test_application_enqueues_and_the_worker_claims(jobs_db):
    db = jobs_db
    owner, organization = _owner_and_organization(db)
    job_id = _enqueue(db, owner, organization, payload={"source_id": "x"})

    _as(db, WORKER_ROLE)
    claimed = [j for j in claim_jobs(db, worker_id="w", limit=50)
               if j.id == job_id]

    assert [(j.status, j.attempts) for j in claimed] == [("running", 1)]
    complete_job(db, claimed[0])
    db.expire_all()
    assert db.get(BackgroundJob, job_id).status == "succeeded"


def test_the_same_key_is_queued_once(jobs_db):
    db = jobs_db
    owner, organization = _owner_and_organization(db)

    first = _enqueue(db, owner, organization, dedupe_key="sync:drive")
    second = _enqueue(db, owner, organization, dedupe_key="sync:drive")

    assert first == second


def test_application_enqueues_only_new_jobs_of_its_organizations(jobs_db):
    db = jobs_db
    owner, organization = _owner_and_organization(db)
    stranger = _create_user(db, "jobs-stranger")
    other = _create_organization(db, stranger)
    _authenticate(db, owner)

    def job(**overrides):
        values = dict(
            id=uuid.uuid4(),
            organization_id=organization.id,
            kind="test.echo",
            payload={},
            created_by_user_id=owner.id,
            run_after=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        values.update(overrides)
        return insert(BackgroundJob).values(**values)

    rls = "row-level security"
    _refused(db, job(organization_id=other.id), rls)
    _refused(db, job(status="running"), rls)
    _refused(db, job(created_by_user_id=stranger.id), rls)
    _refused(db, job(kind="Not A Kind"), "ck_background_jobs_kind")

    job_id = _enqueue(db, owner, organization)
    _refused(
        db,
        update(BackgroundJob)
        .where(BackgroundJob.id == job_id)
        .values(status="cancelled"),
        "permission denied",
    )


def test_other_organizations_do_not_see_the_job(jobs_db):
    db = jobs_db
    owner, organization = _owner_and_organization(db)
    job_id = _enqueue(db, owner, organization)
    stranger = _create_user(db, "jobs-stranger")
    _authenticate(db, stranger)

    db.expire_all()
    assert db.scalars(
        select(BackgroundJob.id).where(BackgroundJob.id == job_id)
    ).all() == []


def test_the_worker_changes_only_the_run_and_only_forward(jobs_db):
    db = jobs_db
    owner, organization = _owner_and_organization(db)
    job_id = _enqueue(db, owner, organization)
    _as(db, WORKER_ROLE)
    row = BackgroundJob.id == job_id

    def change(**values):
        return update(BackgroundJob).where(row).values(**values)

    _refused(db, change(payload={"x": 1}), "permission denied")
    _refused(db, change(status="succeeded"), "invalid job status transition")

    db.execute(change(status="running", attempts=1))
    _refused(db, change(attempts=0), "job attempts cannot decrease")
    db.execute(change(status="failed"))
    _refused(db, change(status="queued"), "a finished job cannot change")


def test_the_worker_reads_nothing_but_jobs(jobs_db):
    db = jobs_db
    _as(db, WORKER_ROLE)

    _refused(db, text("SELECT id FROM users"), "permission denied")
    _refused(db, text("SELECT id FROM email_outbox"), "permission denied")


def test_worker_sessions_run_as_the_worker_role():
    engine = create_engine(TEST_ADMIN_URL)
    try:
        with _session(engine, WORKER_ROLE) as db:
            assert db.execute(text("SELECT current_user")).scalar() == (
                WORKER_ROLE
            )
            db.rollback()
    finally:
        engine.dispose()


def test_the_application_cannot_become_the_worker(postgres_db_session):
    _refused(
        postgres_db_session,
        text("SET ROLE eka_worker"),
        "permission denied",
    )
