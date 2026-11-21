import pytest
from sqlalchemy import text

from app.services import data_gateway
from tests.integration import test_document_permissions as permissions


pytestmark = pytest.mark.integration

perm_db = permissions.perm_db


@pytest.fixture
def world(perm_db):
    return permissions.World(perm_db)


def test_the_gateway_reads_only_the_organization_it_is_asked_for(perm_db, world):
    db = perm_db
    other = permissions.World(db)
    db.flush()
    db.execute(text("SET ROLE eka_worker"))
    db.info.clear()

    mine = data_gateway._connections(db, world.organization)
    assert [c.id for c in mine] == [world.connection]
    db.info.clear()
    theirs = data_gateway._connections(db, other.organization)
    assert [c.id for c in theirs] == [other.connection]
