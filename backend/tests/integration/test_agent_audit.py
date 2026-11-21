import uuid

import pytest
from sqlalchemy import select, text

from app.models import AuditEvent
from tests.integration import test_document_permissions as permissions


pytestmark = pytest.mark.integration

perm_db = permissions.perm_db
_as_runtime = permissions._as_runtime
_refused = permissions._refused


@pytest.fixture
def world(perm_db):
    return permissions.World(perm_db)


def _record(
    db, organization_id, tool="search_documents", step=1, results=3, ms=12, connection_id=None
):
    return text(
        "SELECT app_private.record_agent_tool_call(:o, :tool, :step, :results, :ms, :c)"
    ).bindparams(o=organization_id, tool=tool, step=step, results=results, ms=ms, c=connection_id)


def _tool_calls(db, organization_id):
    db.flush()
    db.execute(text("RESET ROLE"))
    return db.scalars(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization_id,
            AuditEvent.action == "agent.tool_call",
        )
    ).all()


def test_a_member_records_a_tool_call_without_the_person(perm_db, world):
    db = perm_db
    _as_runtime(db, world.ana)
    db.execute(_record(db, world.organization, results=5000, ms=-3))

    [event] = _tool_calls(db, world.organization)
    assert event.actor_user_id is None
    assert event.details == {"tool": "search_documents", "step": 1, "results": 1000, "ms": 0}


def test_an_outsider_cannot_record_tool_calls(perm_db, world):
    db = perm_db
    _as_runtime(db, world.outsider)
    _refused(db, _record(db, world.organization), "not a member")


def test_an_unknown_tool_is_refused(perm_db, world):
    db = perm_db
    _as_runtime(db, world.ana)
    _refused(db, _record(db, world.organization, tool="run_sql"), "unknown tool")


def test_the_limits_are_checked_by_the_database(perm_db, world):
    db = perm_db
    db.flush()
    db.execute(text("RESET ROLE"))
    _refused(
        db,
        text("UPDATE organizations SET agent_max_steps = 9 WHERE id = :o").bindparams(
            o=world.organization
        ),
        "ck_organizations_agent_max_steps",
    )


def test_a_data_query_is_recorded_with_its_connection_only(perm_db, world):
    db = perm_db
    connection = world.connection
    _as_runtime(db, world.ana)
    db.execute(_record(db, world.organization, tool="query_data", results=7, connection_id=connection))

    [event] = _tool_calls(db, world.organization)
    assert event.actor_user_id is None
    assert event.details == {
        "tool": "query_data",
        "connection_id": str(connection),
        "step": 1,
        "results": 7,
        "ms": 12,
    }


def test_a_data_query_must_name_a_connection_of_the_organization(perm_db, world):
    db = perm_db
    _as_runtime(db, world.ana)
    _refused(db, _record(db, world.organization, tool="query_data"), "names its connection")
    _refused(
        db,
        _record(db, world.organization, connection_id=world.connection),
        "names its connection",
    )
    _refused(
        db,
        _record(db, world.organization, tool="query_data", connection_id=uuid.uuid4()),
        "unknown connection",
    )
