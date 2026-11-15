import uuid

import pytest
from sqlalchemy import select

from app.connectors.base import (
    CONNECTORS,
    ChangeSet,
    ConnectorAuthError,
    SourceItem,
)
from app.core.config import settings
from app.models.background_job import BackgroundJob
from app.models.data_connection import DataConnection
from app.models.document import Document, DocumentVersion
from app.services.document_permission_service import SourcePermission
from app.services.object_storage import LocalObjectStorage, StorageKeyError
from app.services.sync_service import sync_connection
from app.services.worker import run_once
from tests.conftest import test_engine


class FakeSource:
    """A source in memory: items, a change cursor, scripted failures."""

    def __init__(self):
        self.items: dict[str, tuple[str, str]] = {}
        self.removed: list[str] = []
        self.complete = False
        self.broken: set[str] = set()
        self.refuse = False
        self.runs = 0

    def add(self, external_id, title, text):
        self.items[external_id] = (title, text)

    def connector(self, context):
        source = self

        class Connector:
            def list_changes(self, cursor):
                if source.refuse:
                    raise ConnectorAuthError("token revoked")
                source.runs += 1
                changed = tuple(
                    SourceItem(
                        external_id=external_id,
                        title=title,
                        mime_type="text/plain",
                        revision=str(source.runs),
                        permissions=(SourcePermission("organization"),),
                    )
                    for external_id, (title, _) in source.items.items()
                )
                removed, source.removed = tuple(source.removed), []
                return ChangeSet(
                    changed=changed,
                    removed=removed,
                    cursor=str(source.runs),
                    complete=source.complete,
                )

            def fetch_text(self, item):
                if item.external_id in source.broken:
                    raise RuntimeError("cannot parse this file")
                return source.items[item.external_id][1]

        return Connector()


@pytest.fixture
def source(monkeypatch):
    fake = FakeSource()
    monkeypatch.setitem(CONNECTORS, "file_upload", fake.connector)
    return fake


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    return LocalObjectStorage(tmp_path)


@pytest.fixture
def connection(client, db_session):
    unique = uuid.uuid4().hex[:8]
    organization = client.post(
        "/api/v1/organizations/",
        json={"name": f"Sync Org {unique}", "slug": f"sync-{unique}"},
    ).json()
    created = client.post(
        f"/api/v1/organizations/{organization['id']}/connections/",
        json={"provider": "file_upload", "name": "Uploads"},
    ).json()
    return db_session.get(DataConnection, uuid.UUID(created["id"]))


def _sync(db, connection, storage):
    summary = sync_connection(db, connection_id=connection.id, storage=storage)
    db.commit()
    db.expire_all()
    return summary


def _documents(db, connection):
    return {
        d.external_id: d
        for d in db.scalars(
            select(Document).where(Document.connection_id == connection.id)
        )
    }


def _versions(db, document):
    return db.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_number)
    ).all()


def test_a_sync_requested_through_the_api_runs_in_the_worker(
    client, db_session, connection, source, storage
):
    source.add("a1", "Vacation policy", "Employees get 22 days.")
    url = (
        f"/api/v1/organizations/{connection.organization_id}/connections/"
        f"{connection.id}/sync"
    )

    first = client.post(url)
    again = client.post(url)
    assert first.status_code == 202
    # Asking twice queues one sync.
    assert again.json()["job_id"] == first.json()["job_id"]

    assert run_once(
        test_engine, worker_id="test", assume_role=None
    )["succeeded"] == 1

    db_session.expire_all()
    [document] = _documents(db_session, connection).values()
    [version] = _versions(db_session, document)
    assert (document.status, document.current_version_id) == (
        "active",
        version.id,
    )
    job = db_session.get(BackgroundJob, uuid.UUID(first.json()["job_id"]))
    assert job.status == "succeeded"
    connection = db_session.get(DataConnection, connection.id)
    assert (connection.sync_cursor, connection.status) == ("1", "active")
    assert connection.last_synced_at is not None


def test_snapshots_are_stored_under_keys_that_reveal_nothing(
    db_session, connection, source, storage
):
    source.add("a1", "Salaries 2026 - confidential", "Line one.\r\n\r\n\r\n")

    _sync(db_session, connection, storage)

    [document] = _documents(db_session, connection).values()
    [version] = _versions(db_session, document)
    key = version.normalized_object_key
    assert "salaries" not in key.lower() and "confidential" not in key
    assert key.startswith(f"{connection.organization_id}/{connection.id}/")
    assert storage.get(key) == b"Line one."
    assert version.size_bytes == len(b"Line one.")


def test_unchanged_content_is_not_reprocessed(
    db_session, connection, source, storage
):
    source.add("a1", "Policy", "Employees get 22 days.")
    assert _sync(db_session, connection, storage)["new_version"] == 1

    source.add("a1", "Policy (renamed)", "Employees get 22 days.\n")
    summary = _sync(db_session, connection, storage)

    assert (summary["new_version"], summary["unchanged"]) == (0, 1)
    document = _documents(db_session, connection)["a1"]
    assert document.title == "Policy (renamed)"
    assert len(_versions(db_session, document)) == 1


def test_changed_content_becomes_the_next_version(
    db_session, connection, source, storage
):
    source.add("a1", "Policy", "Employees get 22 days.")
    _sync(db_session, connection, storage)

    source.add("a1", "Policy", "Employees get 25 days.")
    _sync(db_session, connection, storage)

    document = _documents(db_session, connection)["a1"]
    versions = _versions(db_session, document)
    assert [v.version_number for v in versions] == [1, 2]
    assert document.current_version_id == versions[1].id


def test_removed_items_leave_retrieval_and_can_come_back(
    db_session, connection, source, storage
):
    source.add("a1", "Policy", "text")
    source.add("b2", "Notes", "other text")
    _sync(db_session, connection, storage)

    del source.items["b2"]
    source.removed = ["b2"]
    assert _sync(db_session, connection, storage)["removed"] == 1
    assert _documents(db_session, connection)["b2"].status == "removed"

    source.add("b2", "Notes", "other text")
    assert _sync(db_session, connection, storage)["restored"] == 1
    assert _documents(db_session, connection)["b2"].status == "active"


def test_a_complete_listing_removes_what_it_no_longer_lists(
    db_session, connection, source, storage
):
    source.add("a1", "Policy", "text")
    source.add("b2", "Notes", "other text")
    _sync(db_session, connection, storage)

    source.complete = True
    del source.items["b2"]
    summary = _sync(db_session, connection, storage)

    assert summary["removed"] == 1
    statuses = {k: d.status for k, d in _documents(db_session, connection).items()}
    assert statuses == {"a1": "active", "b2": "removed"}


def test_one_broken_file_does_not_stop_the_others(
    db_session, connection, source, storage
):
    source.add("a1", "Policy", "text")
    source.add("bad", "Scan", "unreadable")
    source.broken = {"bad"}

    summary = _sync(db_session, connection, storage)

    assert (summary["new_version"], summary["failed"]) == (1, 1)
    assert set(_documents(db_session, connection)) == {"a1"}
    connection = db_session.get(DataConnection, connection.id)
    assert connection.status == "active"
    assert "bad: RuntimeError" in connection.last_error


def test_refused_credentials_put_the_connection_in_error(
    db_session, connection, source, storage
):
    source.refuse = True

    _sync(db_session, connection, storage)

    connection = db_session.get(DataConnection, connection.id)
    assert connection.status == "error"
    assert "token revoked" in connection.last_error
    assert connection.sync_cursor is None


def test_paused_connections_are_not_synchronized(
    client, db_session, connection, source, storage
):
    base = (
        f"/api/v1/organizations/{connection.organization_id}/connections/"
        f"{connection.id}"
    )
    source.add("a1", "Policy", "text")
    client.patch(base, json={"status": "paused"})

    assert client.post(f"{base}/sync").status_code == 409
    assert _sync(db_session, connection, storage)["new_version"] == 0
    assert _documents(db_session, connection) == {}


def test_storage_keys_cannot_escape_the_root(tmp_path):
    storage = LocalObjectStorage(tmp_path)

    stored = storage.put("org/doc/abc/normalized.txt", b"hello")
    assert storage.get("org/doc/abc/normalized.txt") == b"hello"
    assert stored.size_bytes == 5 and len(stored.sha256) == 64

    for key in ("../escape.txt", "/etc/passwd", "a/../../b", "Upper/x", ""):
        with pytest.raises(StorageKeyError):
            storage.put(key, b"x")
