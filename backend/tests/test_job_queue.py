import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.background_job import BackgroundJob
from app.services import job_queue
from app.services.job_queue import enqueue_job, job_handler, retry_delay
from app.services.worker import run_once
from tests.conftest import test_engine


CALLS = []


@pytest.fixture
def handlers():
    CALLS.clear()

    @job_handler("test.echo")
    def echo(db, job):
        CALLS.append((job.kind, dict(job.payload), job.attempts))

    @job_handler("test.boom")
    def boom(db, job):
        # Changes made before the failure must not be kept.
        job.payload = {"touched": True}
        raise RuntimeError("source unavailable")

    yield

    job_queue.unregister_job_handler("test.echo")
    job_queue.unregister_job_handler("test.boom")


@pytest.fixture
def organization_id(client):
    unique = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/v1/organizations/",
        json={"name": f"Jobs Org {unique}", "slug": f"jobs-{unique}"},
    )
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


def _enqueue(db, organization_id, user, kind="test.echo", **values):
    job = enqueue_job(
        db,
        organization_id=organization_id,
        kind=kind,
        created_by_user_id=user.id,
        **values,
    )
    db.commit()
    return job.id


def _job(db, job_id):
    db.expire_all()
    return db.get(BackgroundJob, job_id)


def _run(**values):
    return run_once(test_engine, worker_id="test-worker", assume_role=None,
                    **values)


def _make_due(db, job_id):
    job = _job(db, job_id)
    job.run_after = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()


def test_a_job_runs_once_and_succeeds(
    handlers, db_session, organization_id, authenticated_user
):
    job_id = _enqueue(
        db_session,
        organization_id,
        authenticated_user,
        payload={"source_id": "abc"},
    )

    assert _run()["succeeded"] == 1
    assert _run()["succeeded"] == 0

    assert CALLS == [("test.echo", {"source_id": "abc"}, 1)]
    job = _job(db_session, job_id)
    assert job.status == "succeeded"
    assert job.finished_at is not None
    assert (job.locked_by, job.attempts) == ("test-worker", 1)


def test_the_same_key_is_not_queued_twice(
    handlers, db_session, organization_id, authenticated_user
):
    first = _enqueue(
        db_session, organization_id, authenticated_user, dedupe_key="sync:1"
    )
    second = _enqueue(
        db_session, organization_id, authenticated_user, dedupe_key="sync:1"
    )
    assert first == second

    _run()
    # Once finished, the same work can be asked for again.
    third = _enqueue(
        db_session, organization_id, authenticated_user, dedupe_key="sync:1"
    )
    assert third != first


def test_failures_roll_back_and_retry_with_backoff_then_fail(
    handlers, db_session, organization_id, authenticated_user
):
    job_id = _enqueue(
        db_session, organization_id, authenticated_user, kind="test.boom"
    )
    max_attempts = _job(db_session, job_id).max_attempts

    for attempt in range(1, max_attempts):
        assert _run()["retrying"] == 1
        job = _job(db_session, job_id)
        assert (job.status, job.attempts) == ("queued", attempt)
        assert job.last_error == "RuntimeError: source unavailable"
        assert job.payload == {}
        # Not due yet: the next pass leaves it alone.
        assert _run()["retrying"] == 0
        _make_due(db_session, job_id)

    assert _run()["failed"] == 1
    job = _job(db_session, job_id)
    assert (job.status, job.attempts) == ("failed", max_attempts)
    assert job.finished_at is not None


def test_a_job_nobody_handles_fails_at_once(
    handlers, db_session, organization_id, authenticated_user
):
    job_id = _enqueue(
        db_session, organization_id, authenticated_user, kind="test.unknown"
    )

    assert _run()["failed"] == 1
    job = _job(db_session, job_id)
    assert job.status == "failed"
    assert job.last_error.startswith("UnknownJobKindError")


def test_a_job_lost_by_a_stopped_worker_is_run_again(
    handlers, db_session, organization_id, authenticated_user
):
    job_id = _enqueue(db_session, organization_id, authenticated_user)
    job = _job(db_session, job_id)
    job.status = "running"
    job.attempts = 1
    job.locked_by = "stopped-worker"
    job.locked_at = datetime.now(timezone.utc) - job_queue.LEASE * 2
    db_session.commit()

    outcome = _run()

    assert (outcome["requeued"], outcome["succeeded"]) == (1, 1)
    assert _job(db_session, job_id).attempts == 2


def test_a_job_that_keeps_stopping_its_worker_gives_up(
    handlers, db_session, organization_id, authenticated_user
):
    job_id = _enqueue(db_session, organization_id, authenticated_user)
    job = _job(db_session, job_id)
    job.status = "running"
    job.attempts = job.max_attempts
    job.locked_at = datetime.now(timezone.utc) - job_queue.LEASE * 2
    db_session.commit()

    assert _run()["succeeded"] == 0
    assert _job(db_session, job_id).status == "failed"


def test_retry_delay_doubles_up_to_an_hour():
    assert retry_delay(1) == timedelta(seconds=30)
    assert retry_delay(2) == timedelta(minutes=1)
    assert retry_delay(4) == timedelta(minutes=4)
    assert retry_delay(20) == timedelta(hours=1)


def test_a_kind_has_one_handler(handlers):
    with pytest.raises(ValueError):
        job_handler("test.echo")(lambda db, job: None)


def test_a_worker_session_carries_an_organization_but_no_user(db_session):
    from app.db.context import set_identity_context, set_worker_context

    organization_id = uuid.uuid4()
    set_worker_context(db_session, organization_id=organization_id)
    assert db_session.info["organization_id"] == str(organization_id)
    assert db_session.info["user_id"] is None

    set_identity_context(
        db_session,
        issuer="https://issuer.example.com/",
        subject="someone",
        user_id=uuid.uuid4(),
    )
    with pytest.raises(RuntimeError):
        set_worker_context(db_session, organization_id=organization_id)
