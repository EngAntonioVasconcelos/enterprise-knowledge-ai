import pytest
from sqlalchemy import text

from app.db.context import set_organization_context
from app.services.connection_service import update_connection
from app.services.document_permission_service import SourcePermission
from tests.integration import test_document_permissions as permissions
from tests.integration.test_document_permissions import _as_runtime


pytestmark = pytest.mark.integration

perm_db = permissions.perm_db


@pytest.fixture
def world(perm_db):
    return permissions.World(perm_db)


def _scope(db, world, scope):
    _as_runtime(db, world.owner)
    set_organization_context(db, organization_id=world.organization)
    update_connection(
        db,
        organization_id=world.organization,
        connection_id=world.connection,
        settings={} if scope is None else {"scope": scope},
    )
    db.flush()


def _set_role(db, world, user_id, role):
    db.flush()
    db.execute(text("RESET ROLE"))
    db.execute(
        text(
            "UPDATE organization_memberships SET role = :role, "
            "has_held_privileged_role = true, updated_at = now() "
            "WHERE organization_id = :organization AND user_id = :user"
        ),
        {"role": role, "organization": world.organization, "user": user_id},
    )
    db.execute(text("SET ROLE eka_runtime"))
    db.expire_all()


def test_a_scope_only_removes_readers_and_can_be_lifted(perm_db, world):
    db = perm_db
    everyone = world.document(db, [SourcePermission("organization")])
    only_ana = world.document(db, [SourcePermission("user", f"ana@{world.domain}")])
    assert world.readers(db, everyone) == ["owner", "ana", "rui"]

    _scope(db, world, {"roles": ["owner", "admin"]})

    assert world.readers(db, everyone) == ["owner"]
    # The scope never grants: the owner still cannot open Ana's document.
    assert world.readers(db, only_ana) == []

    _scope(db, world, None)

    assert world.readers(db, everyone) == ["owner", "ana", "rui"]
    assert world.readers(db, only_ana) == ["ana"]


def test_documents_synced_later_follow_the_scope(perm_db, world):
    db = perm_db
    _scope(db, world, {"roles": ["member"]})

    document = world.document(db, [SourcePermission("domain", world.domain)])

    assert world.readers(db, document) == ["ana", "rui"]


def test_a_new_role_takes_effect_at_once(perm_db, world):
    db = perm_db
    document = world.document(db, [SourcePermission("organization")])
    _scope(db, world, {"roles": ["owner", "admin"]})
    assert world.readers(db, document) == ["owner"]

    _set_role(db, world, world.ana, "admin")

    assert world.readers(db, document) == ["owner", "ana"]
