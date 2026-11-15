import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.connectors.base import CONNECTORS, ChangeSet, SourceItem
from app.core.errors import InvalidInputError
from app.models.background_job import BackgroundJob
from app.services import embeddings
from app.services.document_permission_service import SourcePermission
from app.services.embedding_service import EMBED_JOB, embed_version
from app.services.object_storage import LocalObjectStorage
from app.services.search_service import search
from app.services.sync_service import sync_connection
from tests.integration import test_document_permissions as permissions


pytestmark = pytest.mark.integration

perm_db = permissions.perm_db
_as_runtime = permissions._as_runtime
_as_worker = permissions._as_worker

HANDBOOK = (
    "4.2 Ferias\n\n"
    "Cada colaborador tem direito a 25 dias uteis de ferias por ano.\n\n"
    "5. Parking\n\nThe parking lot closes at 8 pm.\n"
)
SALARIES = "Salary bands\n\nEngineering salary bands are confidential.\n"


@pytest.fixture
def hashing(monkeypatch):
    embeddings._cached.cache_clear()
    monkeypatch.setattr(embeddings.settings, "EMBEDDING_PROVIDER", "hashing")
    yield
    embeddings._cached.cache_clear()


@pytest.fixture
def world(perm_db):
    return permissions.World(perm_db)


@pytest.fixture
def embedded(perm_db, world, hashing, tmp_path, monkeypatch):
    db = perm_db
    items = {
        "handbook": (HANDBOOK, (SourcePermission("domain", world.domain),)),
        "salaries": (SALARIES, (SourcePermission("user", f"ana@{world.domain}"),)),
    }

    class Connector:
        def list_changes(self, cursor):
            return ChangeSet(
                changed=tuple(
                    SourceItem(key, key.title(), permissions=perms, revision="1")
                    for key, (body, perms) in items.items()
                ),
                cursor="token",
            )

        def fetch_text(self, item):
            return items[item.external_id][0]

    monkeypatch.setitem(CONNECTORS, "google_drive", lambda context: Connector())
    _as_worker(db, world.organization)
    sync_connection(db, connection_id=world.connection, storage=LocalObjectStorage(tmp_path))
    db.flush()

    jobs = db.scalars(
        select(BackgroundJob).where(
            BackgroundJob.organization_id == world.organization,
            BackgroundJob.kind == EMBED_JOB,
        )
    ).all()
    assert len(jobs) == 2
    assert all(job.created_by_user_id is None for job in jobs)
    for job in jobs:
        assert embed_version(db, version_id=uuid.UUID(job.payload["version_id"])) > 0
    db.flush()
    return jobs


def _search(db, world, user_id, query, mode="hybrid"):
    _as_runtime(db, user_id)
    return search(db, organization_id=world.organization, query=query, mode=mode)


def test_the_sync_queues_vectors_and_the_worker_computes_them(perm_db, world, embedded):
    db = perm_db
    _as_worker(db, world.organization)
    rows = db.execute(text("SELECT model, dims FROM chunk_embeddings")).all()
    assert rows and {tuple(r) for r in rows} == {("test/hashing-384", 384)}


def test_search_by_meaning_and_hybrid(perm_db, world, embedded):
    semantic = _search(perm_db, world, world.rui, "dias de ferias", mode="semantic")
    assert semantic.mode == "semantic"
    assert semantic.hits[0].heading == "4.2 Ferias"
    assert semantic.hits[0].semantic_rank == 1

    hybrid = _search(perm_db, world, world.rui, "dias de ferias")
    assert hybrid.mode == "hybrid" and hybrid.note is None
    top = hybrid.hits[0]
    assert top.heading == "4.2 Ferias"
    assert (top.keyword_rank, top.semantic_rank) == (1, 1)


def test_vectors_follow_document_permissions(perm_db, world, embedded):
    db = perm_db
    assert [h.title for h in _search(db, world, world.ana, "salary bands", "semantic").hits][0] == "Salaries"
    assert all(
        h.title != "Salaries"
        for h in _search(db, world, world.owner, "salary bands", "semantic").hits
    )

    def visible_vectors(user_id):
        _as_runtime(db, user_id)
        return db.execute(text("SELECT count(*) FROM chunk_embeddings")).scalar()

    assert visible_vectors(world.ana) > visible_vectors(world.rui) > 0
    assert visible_vectors(world.outsider) == 0


def test_only_the_worker_writes_vectors(perm_db, world, embedded):
    db = perm_db
    _as_runtime(db, world.ana)
    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            db.execute(text("DELETE FROM chunk_embeddings"))
    assert "permission denied" in str(error.value.orig)


def test_the_worker_may_queue_only_vector_jobs(perm_db, world, embedded):
    db = perm_db
    _as_worker(db, world.organization)
    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            db.execute(
                text(
                    "INSERT INTO background_jobs (id, organization_id, kind, payload, "
                    "status, attempts, max_attempts, run_after, created_at) "
                    "VALUES (gen_random_uuid(), :org, 'connection.sync', '{}', 'queued', 0, 5, "
                    "now(), now())"
                ),
                {"org": world.organization},
            )
    assert "row-level security" in str(error.value.orig)


def test_hybrid_falls_back_to_words_without_vectors(perm_db, world, embedded, monkeypatch):
    embeddings._cached.cache_clear()
    monkeypatch.setattr(embeddings.settings, "EMBEDDING_PROVIDER", "none")

    result = _search(perm_db, world, world.rui, "dias de ferias")
    assert result.mode == "keyword" and "unavailable" in result.note
    assert result.hits[0].heading == "4.2 Ferias"

    with pytest.raises(InvalidInputError):
        _search(perm_db, world, world.rui, "dias de ferias", mode="semantic")
