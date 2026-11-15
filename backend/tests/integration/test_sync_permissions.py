import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from app.connectors.base import CONNECTORS, ChangeSet, SourceItem
from app.models import DataConnection, Document
from app.services.document_permission_service import SourcePermission
from app.services.object_storage import LocalObjectStorage
from app.services.sync_service import sync_connection
from tests.integration import test_document_permissions as permissions


pytestmark = pytest.mark.integration

# The same scenario as the permission tests: an organization at a test
# domain with an owner, two members and an outsider.
perm_db = permissions.perm_db
_as_runtime = permissions._as_runtime
_as_worker = permissions._as_worker


@pytest.fixture
def world(perm_db):
    return permissions.World(perm_db)


def test_a_sync_brings_documents_readable_only_as_the_source_allows(
    perm_db, world, tmp_path, monkeypatch
):
    db = perm_db
    ana = f"ana@{world.domain}"

    class Connector:
        def list_changes(self, cursor):
            return ChangeSet(
                changed=(
                    SourceItem(
                        "f-1",
                        "Ana's notes",
                        permissions=(SourcePermission("user", ana),),
                    ),
                    SourceItem(
                        "f-2",
                        "Handbook",
                        permissions=(
                            SourcePermission("domain", world.domain),
                        ),
                    ),
                ),
                cursor="token-1",
            )

        def fetch_text(self, item):
            return f"content of {item.external_id}"

    monkeypatch.setitem(CONNECTORS, "google_drive", lambda context: Connector())

    _as_worker(db, world.organization)
    summary = sync_connection(
        db,
        connection_id=world.connection,
        storage=LocalObjectStorage(tmp_path),
    )
    assert summary["new_version"] == 2
    db.flush()

    def titles(user_id):
        _as_runtime(db, user_id)
        return sorted(db.scalars(select(Document.title)).all())

    assert titles(world.ana) == ["Ana's notes", "Handbook"]
    assert titles(world.rui) == ["Handbook"]
    assert titles(world.owner) == ["Handbook"]
    assert titles(world.outsider) == []


def test_only_the_worker_moves_the_sync_cursor(perm_db, world):
    db = perm_db
    _as_runtime(db, world.owner)

    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            db.execute(
                update(DataConnection)
                .where(DataConnection.id == world.connection)
                .values(sync_cursor="skip-everything")
            )
    assert "permission denied" in str(error.value.orig)

    _as_worker(db, world.organization)
    db.execute(
        update(DataConnection)
        .where(DataConnection.id == world.connection)
        .values(sync_cursor="token-2")
    )
    assert db.execute(
        text("SELECT sync_cursor FROM data_connections WHERE id = :id"),
        {"id": world.connection},
    ).scalar() == "token-2"
