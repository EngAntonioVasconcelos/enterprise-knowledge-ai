import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import func, insert, select, text, update

from app.models import AnswerEvent
from app.services import dashboard_service
from tests.integration import test_document_permissions as permissions


pytestmark = pytest.mark.integration

perm_db = permissions.perm_db
_as_runtime = permissions._as_runtime
_refused = permissions._refused


@pytest.fixture
def world(perm_db):
    return permissions.World(perm_db)


def _count_as(db, world, user_id):
    _as_runtime(db, user_id)
    dashboard_service.record_event(
        db,
        organization_id=world.organization,
        abstained=False,
        verified=True,
        language="pt",
        cited_document_ids=[],
    )


def _visible(db, user_id):
    _as_runtime(db, user_id)
    return db.scalar(select(func.count()).select_from(AnswerEvent))


def test_members_count_answers_and_only_managers_read_the_counts(perm_db, world):
    db = perm_db
    _count_as(db, world, world.ana)
    _count_as(db, world, world.rui)

    assert _visible(db, world.owner) == 2
    assert _visible(db, world.ana) == 0
    assert _visible(db, world.outsider) == 0

    _as_runtime(db, world.owner)
    assert dashboard_service.build_dashboard(db, organization_id=world.organization)["questions"] == 2


def test_nobody_counts_for_another_organization_or_another_day(perm_db, world):
    db = perm_db
    row = dict(
        id=uuid.uuid4(),
        organization_id=world.organization,
        abstained=False,
        verified=True,
        language="pt",
        cited_document_ids=[],
    )
    _as_runtime(db, world.outsider)
    _refused(db, insert(AnswerEvent).values(**row), "row-level security")

    _as_runtime(db, world.ana)
    yesterday = date.today() - timedelta(days=1)
    _refused(
        db,
        insert(AnswerEvent).values(**{**row, "answered_on": yesterday}),
        "row-level security",
    )


def test_counts_cannot_be_changed(perm_db, world):
    db = perm_db
    _count_as(db, world, world.ana)
    _as_runtime(db, world.owner)
    _refused(db, update(AnswerEvent).values(abstained=True), "permission denied")


def test_the_worker_deletes_counts_older_than_a_year(perm_db, world):
    db = perm_db
    _count_as(db, world, world.ana)
    _count_as(db, world, world.ana)
    db.flush()
    db.execute(text("RESET ROLE"))
    db.execute(
        text(
            "UPDATE answer_events SET answered_on = CURRENT_DATE - 400 "
            "WHERE id = (SELECT id FROM answer_events "
            "WHERE organization_id = :o LIMIT 1)"
        ),
        {"o": world.organization},
    )
    db.execute(text("SET ROLE eka_worker"))
    _refused(db, select(AnswerEvent), "permission denied")
    assert dashboard_service.purge_old_events(db) >= 1
    assert _visible(db, world.owner) == 1


def test_gaps_hold_only_ids_and_a_known_reason(perm_db, world):
    db = perm_db
    _as_runtime(db, world.ana)
    document = uuid.uuid4()
    dashboard_service.record_event(
        db,
        organization_id=world.organization,
        abstained=True,
        verified=True,
        language="pt",
        cited_document_ids=[],
        consulted_document_ids=[document],
        gap_reason="not_found",
    )
    row = dict(
        id=uuid.uuid4(),
        organization_id=world.organization,
        abstained=False,
        verified=True,
        language="pt",
        cited_document_ids=[],
    )
    _refused(db, insert(AnswerEvent).values(**row, gap_reason="not_found"), "ck_answer_events_gap_reason")
    _refused(
        db,
        insert(AnswerEvent).values(**{**row, "abstained": True}, gap_reason="secret"),
        "ck_answer_events_gap_reason",
    )
    _as_runtime(db, world.owner)
    gaps = dashboard_service.build_gaps(db, organization_id=world.organization)
    assert gaps["reasons"]["not_found"] == 1 and gaps["hidden_documents"] == 0
