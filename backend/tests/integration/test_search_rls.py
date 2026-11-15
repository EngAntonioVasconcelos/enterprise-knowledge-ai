import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.connectors.base import CONNECTORS, ChangeSet, SourceItem
from app.services.document_permission_service import SourcePermission
from app.services.object_storage import LocalObjectStorage
from app.services.search_service import search_text
from app.services.sync_service import sync_connection
from tests.integration import test_document_permissions as permissions


pytestmark = pytest.mark.integration

perm_db = permissions.perm_db
_as_runtime = permissions._as_runtime
_as_worker = permissions._as_worker

HANDBOOK = (
    "1. Welcome\n\nThe company was founded in 2010.\n\n"
    "4.2 F\u00e9rias\n\n"
    "Cada colaborador tem direito a 25 dias \u00fateis de f\u00e9rias por ano.\n"
)
SALARIES = "Salary bands\n\nThe band for engineers is confidential: code C-2041.\n"


@pytest.fixture
def world(perm_db):
    return permissions.World(perm_db)


@pytest.fixture
def synced(perm_db, world, tmp_path, monkeypatch):
    """A handbook for the whole domain and a salary file only for Ana."""
    db = perm_db
    items = {
        "handbook": (HANDBOOK, (SourcePermission("domain", world.domain),)),
        "salaries": (SALARIES, (SourcePermission("user", f"ana@{world.domain}"),)),
    }

    class Connector:
        def list_changes(self, cursor):
            return ChangeSet(
                changed=tuple(
                    SourceItem(key, key.title(), permissions=perms, revision=str(len(body)))
                    for key, (body, perms) in items.items()
                ),
                cursor="token",
            )

        def fetch_text(self, item):
            return items[item.external_id][0]

    monkeypatch.setitem(CONNECTORS, "google_drive", lambda context: Connector())
    _as_worker(db, world.organization)
    summary = sync_connection(
        db, connection_id=world.connection, storage=LocalObjectStorage(tmp_path)
    )
    assert summary["new_version"] == 2
    db.flush()
    return items


def _search(db, world, user_id, query):
    _as_runtime(db, user_id)
    return search_text(db, organization_id=world.organization, query=query)


def test_a_sync_makes_documents_searchable_in_passages(perm_db, world, synced):
    hits = _search(perm_db, world, world.rui, "dias de f\u00e9rias")

    assert [hit.title for hit in hits] == ["Handbook"]
    hit = hits[0]
    assert hit.heading == "4.2 F\u00e9rias"
    assert "25 dias" in hit.snippet
    # The position points at the passage inside the stored text.
    assert HANDBOOK[hit.start_char:hit.end_char].startswith("4.2 F\u00e9rias")


def test_accents_and_case_are_ignored(perm_db, world, synced):
    assert [h.title for h in _search(perm_db, world, world.rui, "FERIAS uteis")] == ["Handbook"]


def test_only_passages_of_readable_documents_are_found(perm_db, world, synced):
    assert [h.title for h in _search(perm_db, world, world.ana, "C-2041")] == ["Salaries"]
    # The owner manages the organization but cannot open Ana's file.
    assert _search(perm_db, world, world.owner, "C-2041") == []
    assert _search(perm_db, world, world.rui, "confidential") == []
    assert _search(perm_db, world, world.outsider, "f\u00e9rias") == []


def test_the_runtime_cannot_write_chunks(perm_db, world, synced):
    db = perm_db
    _as_runtime(db, world.ana)
    for statement in (
        "DELETE FROM document_chunks",
        "UPDATE document_chunks SET content = 'x'",
    ):
        with pytest.raises(DBAPIError) as error:
            with db.begin_nested():
                db.execute(text(statement))
        assert "permission denied" in str(error.value.orig)


def test_the_worker_writes_chunks_only_for_its_organization(perm_db, world, synced):
    db = perm_db
    _as_worker(db, world.organization)
    assert db.execute(text("SELECT count(*) FROM document_chunks")).scalar() >= 2

    _as_runtime(db, world.owner)
    other = permissions.World(db)
    _as_worker(db, other.organization)
    assert db.execute(text("SELECT count(*) FROM document_chunks")).scalar() == 0


def test_a_removed_document_is_no_longer_found(perm_db, world, synced, tmp_path, monkeypatch):
    db = perm_db
    del synced["salaries"]

    class Connector:
        def list_changes(self, cursor):
            return ChangeSet(changed=(), removed=("salaries",), cursor="token-2")

        def fetch_text(self, item):
            raise AssertionError("nothing to read")

    monkeypatch.setitem(CONNECTORS, "google_drive", lambda context: Connector())
    _as_worker(db, world.organization)
    sync_connection(db, connection_id=world.connection, storage=LocalObjectStorage(tmp_path))
    db.flush()

    assert _search(db, world, world.ana, "C-2041") == []


def test_a_new_version_replaces_the_old_passages(perm_db, world, synced, tmp_path, monkeypatch):
    db = perm_db

    class Connector:
        def list_changes(self, cursor):
            return ChangeSet(
                changed=(
                    SourceItem(
                        "handbook",
                        "Handbook",
                        permissions=(SourcePermission("domain", world.domain),),
                        revision="v2",
                    ),
                ),
                cursor="token-3",
            )

        def fetch_text(self, item):
            return "4.2 F\u00e9rias\n\nAgora s\u00e3o 30 dias de f\u00e9rias.\n"

    monkeypatch.setitem(CONNECTORS, "google_drive", lambda context: Connector())
    _as_worker(db, world.organization)
    sync_connection(db, connection_id=world.connection, storage=LocalObjectStorage(tmp_path))
    db.flush()

    hits = _search(db, world, world.rui, "dias de f\u00e9rias")
    assert len(hits) == 1 and "30 dias" in hits[0].snippet
    assert _search(db, world, world.rui, "uteis") == []


def test_empty_or_huge_searches_are_refused(perm_db, world):
    from app.core.errors import InvalidInputError

    _as_runtime(perm_db, world.ana)
    for query in ("   ", "x" * 501):
        with pytest.raises(InvalidInputError):
            search_text(perm_db, organization_id=world.organization, query=query)


def test_search_ids_are_uuids(perm_db, world, synced):
    hit = _search(perm_db, world, world.rui, "founded")[0]
    assert isinstance(hit.chunk_id, uuid.UUID) and hit.score > 0
