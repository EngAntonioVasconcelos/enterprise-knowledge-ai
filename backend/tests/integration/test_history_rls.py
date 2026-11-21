import uuid

import pytest
from sqlalchemy import insert, select, text, update

from app.models import AuditEvent, Organization, QuestionHistory
from app.services import history_service
from tests.integration import test_document_permissions as permissions


pytestmark = pytest.mark.integration

perm_db = permissions.perm_db
_as_runtime = permissions._as_runtime
_refused = permissions._refused


@pytest.fixture
def world(perm_db):
    return permissions.World(perm_db)


def _ask_as(db, world, user_id, question="Quantos dias de ferias tenho?"):
    _as_runtime(db, user_id)
    organization = db.get(Organization, world.organization)
    entry = history_service.record_answer(
        db,
        organization=organization,
        user_id=user_id,
        question=question,
        answer="Tens 25 dias uteis [1].",
        abstained=False,
        verified=True,
        language="pt",
        sources=[],
    )
    db.flush()
    return entry.id


def _questions(db, user_id):
    _as_runtime(db, user_id)
    return db.scalars(select(QuestionHistory.question)).all()


def test_only_the_person_who_asked_reads_the_question(perm_db, world):
    db = perm_db
    _ask_as(db, world, world.ana, "pergunta da ana")
    _ask_as(db, world, world.rui, "pergunta do rui")

    assert _questions(db, world.ana) == ["pergunta da ana"]
    assert _questions(db, world.rui) == ["pergunta do rui"]
    # Not even the owner reads other people's questions.
    assert _questions(db, world.owner) == []
    assert _questions(db, world.outsider) == []


def test_nobody_writes_or_deletes_for_someone_else(perm_db, world):
    db = perm_db
    entry = _ask_as(db, world, world.ana)

    _as_runtime(db, world.rui)
    _refused(
        db,
        insert(QuestionHistory).values(
            id=uuid.uuid4(),
            organization_id=world.organization,
            user_id=world.ana,
            question="forjada",
            answer="",
            abstained=True,
            verified=False,
            language="pt",
            sources=[],
        ),
        "row-level security",
    )
    assert not history_service.delete_entry(
        db, organization_id=world.organization, user_id=world.ana, entry_id=entry
    )
    db.execute(text("DELETE FROM question_history"))
    assert _questions(db, world.ana) == ["Quantos dias de ferias tenho?"]

    _as_runtime(db, world.ana)
    assert history_service.delete_entry(
        db, organization_id=world.organization, user_id=world.ana, entry_id=entry
    )
    assert _questions(db, world.ana) == []


def test_rows_cannot_be_changed(perm_db, world):
    db = perm_db
    _ask_as(db, world, world.ana)
    _as_runtime(db, world.ana)
    _refused(
        db,
        update(QuestionHistory).values(answer="outra"),
        "permission denied",
    )


def test_no_history_is_kept_when_the_organization_keeps_none(perm_db, world):
    db = perm_db
    _as_runtime(db, world.owner)
    db.execute(
        update(Organization)
        .where(Organization.id == world.organization)
        .values(history_retention_days=0)
    )
    db.flush()

    _as_runtime(db, world.ana)
    _refused(
        db,
        insert(QuestionHistory).values(
            id=uuid.uuid4(),
            organization_id=world.organization,
            user_id=world.ana,
            question="q",
            answer="",
            abstained=True,
            verified=False,
            language="pt",
            sources=[],
        ),
        "row-level security",
    )

    _as_runtime(db, world.owner)
    actions = db.scalars(
        select(AuditEvent.details).where(
            AuditEvent.organization_id == world.organization,
            AuditEvent.action == "organization.history_retention_changed",
        )
    ).all()
    assert actions == [{"from": 90, "to": 0}]


def test_members_cannot_change_how_long_questions_are_kept(perm_db, world):
    db = perm_db
    _as_runtime(db, world.ana)
    changed = db.execute(
        update(Organization)
        .where(Organization.id == world.organization)
        .values(history_retention_days=365)
    ).rowcount
    assert changed == 0


def test_the_worker_deletes_old_questions_without_reading_them(perm_db, world):
    db = perm_db
    old = _ask_as(db, world, world.ana, "antiga")
    _ask_as(db, world, world.ana, "recente")
    db.execute(text("RESET ROLE"))
    db.execute(
        text(
            "UPDATE question_history SET created_at = now() - interval '91 days' "
            "WHERE id = :id"
        ),
        {"id": old},
    )

    db.execute(text("SET ROLE eka_worker"))
    _refused(db, select(QuestionHistory), "permission denied")
    assert history_service.purge_expired(db) == 1

    assert _questions(db, world.ana) == ["recente"]
