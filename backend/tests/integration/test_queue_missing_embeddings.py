import pytest
from sqlalchemy import select, text

from app.models.background_job import BackgroundJob
from app.services.embedding_service import EMBED_JOB
from scripts import queue_missing_embeddings as script
from scripts.prepare_test_database import TEST_ADMIN_URL
from tests.integration import test_document_permissions as permissions
from tests.integration import test_hybrid_search as hybrid


pytestmark = pytest.mark.integration

perm_db = permissions.perm_db
hashing = hybrid.hashing
world = hybrid.world
embedded = hybrid.embedded

MODEL = "test/hashing-384"


def _ours(db, world, versions):
    """Keep only versions of this test's organization (others may exist)."""
    ids = set(
        db.execute(
            text("SELECT current_version_id FROM documents WHERE organization_id = :o"),
            {"o": world.organization},
        ).scalars()
    )
    return [v for v in versions if v in ids]


def _waiting(db, world):
    return db.scalars(
        select(BackgroundJob).where(
            BackgroundJob.organization_id == world.organization,
            BackgroundJob.kind == EMBED_JOB,
            BackgroundJob.status.in_(("queued", "running")),
        )
    ).all()


def _fail_every_job(db):
    """As the worker does after the last attempt (the database allows only
    queued -> running -> failed)."""
    for status in ("running", "failed"):
        db.execute(text("UPDATE background_jobs SET status = :s WHERE kind = :k"), {"s": status, "k": EMBED_JOB})


def test_versions_with_vectors_are_left_alone(perm_db, world, embedded):
    db = perm_db
    db.execute(text("RESET ROLE"))
    _fail_every_job(db)
    assert _ours(db, world, script.missing_versions(db, model=MODEL)) == []


def test_failed_jobs_are_queued_again_once(perm_db, world, embedded):
    db = perm_db
    db.execute(text("RESET ROLE"))
    # The vectors of another model are missing and every job has failed.
    _fail_every_job(db)
    assert len(_ours(db, world, script.missing_versions(db, model="other/model"))) == 2

    script.queue_missing(db, model="other/model")
    jobs = _waiting(db, world)
    assert len(jobs) == 2
    assert all(job.created_by_user_id is None and job.attempts == 0 for job in jobs)
    vectors = db.execute(text("SELECT count(*) FROM chunk_embeddings")).scalar()

    # A second run finds the jobs waiting and adds nothing.
    assert _ours(db, world, script.missing_versions(db, model="other/model")) == []
    script.queue_missing(db, model="other/model")
    assert len(_waiting(db, world)) == 2
    # Queuing never touches the vectors already there.
    assert db.execute(text("SELECT count(*) FROM chunk_embeddings")).scalar() == vectors


def test_it_stops_without_the_administrator_url(monkeypatch, capsys):
    monkeypatch.setattr(script.settings, "MIGRATION_DATABASE_URL", None)
    assert script.main([]) == 1
    assert "MIGRATION_DATABASE_URL" in capsys.readouterr().out


def test_it_only_counts_without_apply(postgres_engine, hashing, monkeypatch, capsys):
    monkeypatch.setattr(script.settings, "MIGRATION_DATABASE_URL", TEST_ADMIN_URL)
    monkeypatch.setattr(script.settings, "EMBEDDING_MODEL", "other/model")
    count_jobs = text("SELECT count(*) FROM background_jobs")
    with postgres_engine.connect() as connection:
        before = connection.execute(count_jobs).scalar()
    assert script.main([]) == 0
    assert "Documents without vectors" in capsys.readouterr().out
    with postgres_engine.connect() as connection:
        assert connection.execute(count_jobs).scalar() == before
