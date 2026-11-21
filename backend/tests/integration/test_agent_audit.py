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


def _record(db, organization_id, tool="search_documents", step=1, results=3, ms=12):
    return text(
        "SELECT app_private.record_agent_tool_call(:o, :tool, :step, :results, :ms)"
    ).bindparams(o=organization_id, tool=tool, step=step, results=results, ms=ms)


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
