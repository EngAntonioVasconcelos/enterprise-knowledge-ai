import uuid

import pytest

from app.models import AnswerEvent, Document
from app.services.answer_service import NOT_RELEVANT, Source, gap_reason
from tests.test_history import _ask, _hit, _result


@pytest.fixture
def organization(client):
    return client.post(
        "/api/v1/organizations/",
        json={"name": "Dashboard Org", "slug": f"dashboard-{uuid.uuid4().hex[:8]}"},
    ).json()


def _dashboard(client, organization):
    response = client.get(f"/api/v1/organizations/{organization['id']}/dashboard/")
    assert response.status_code == 200, response.text
    return response.json()


def test_answers_are_counted_without_people_or_text(client, db_session, monkeypatch, organization):
    document = uuid.uuid4()
    db_session.add(
        Document(
            id=document,
            organization_id=uuid.UUID(organization["id"]),
            connection_id=uuid.uuid4(),
            external_id="manual",
            title="Manual do Colaborador",
            status="active",
            current_version_id=uuid.uuid4(),
        )
    )
    db_session.flush()
    _ask(client, monkeypatch, organization, _result(document_id=document))
    _ask(client, monkeypatch, organization, _result(document_id=document))

    event = db_session.query(AnswerEvent).first()
    # Nothing in the row says who asked or what.
    assert not {"user_id", "question", "answer"} & set(AnswerEvent.__table__.columns.keys())
    assert event.cited_document_ids == [str(document)]

    body = _dashboard(client, organization)
    assert body["questions"] == 2 and body["unanswered"] == 0
    assert len(body["days"]) == 30 and body["days"][-1]["questions"] == 2
    assert body["languages"] == {"pt": 2, "en": 0, "fr": 0}
    assert body["top_documents"] == [
        {"document_id": str(document), "title": "Manual do Colaborador", "citations": 2}
    ]
    assert body["members"] == 1


def test_documents_the_viewer_cannot_open_are_not_named(client, monkeypatch, organization):
    # The cited document is not readable (here: it does not exist).
    _ask(client, monkeypatch, organization)
    assert _dashboard(client, organization)["top_documents"] == []


def test_answers_are_counted_even_without_history(client, monkeypatch, organization):
    client.patch(
        f"/api/v1/organizations/{organization['id']}",
        json={"history_retention_days": 0},
    )
    _ask(client, monkeypatch, organization)
    assert _dashboard(client, organization)["questions"] == 1


def test_another_organization_is_refused(client):
    response = client.get(f"/api/v1/organizations/{uuid.uuid4()}/dashboard/")
    assert response.status_code in (403, 404)


def _no_answer(*document_ids, issues=()):
    result = _result()
    result.abstained, result.verified, result.cited = True, not issues, []
    result.answer = "Nao encontrei uma resposta fiavel."
    result.issues = list(issues)
    result.sources = [
        Source(n, _hit(document_id, uuid.uuid4(), f"Doc {n}"))
        for n, document_id in enumerate(document_ids, start=1)
    ]
    return result


def _gaps(client, organization):
    response = client.get(f"/api/v1/organizations/{organization['id']}/dashboard/gaps")
    assert response.status_code == 200, response.text
    return response.json()


def _readable(db, organization, title):
    document = uuid.uuid4()
    db.add(
        Document(
            id=document,
            organization_id=uuid.UUID(organization["id"]),
            connection_id=uuid.uuid4(),
            external_id=title,
            title=title,
            status="active",
            current_version_id=uuid.uuid4(),
        )
    )
    db.flush()
    return document


def test_gap_reasons():
    assert gap_reason(_result()) is None
    assert gap_reason(_no_answer()) == "no_sources"
    assert gap_reason(_no_answer(uuid.uuid4())) == "not_found"
    assert gap_reason(_no_answer(uuid.uuid4(), issues=["cites no source"])) == "checks"
    assert gap_reason(_no_answer(uuid.uuid4(), issues=[NOT_RELEVANT])) == "not_relevant"


def test_gaps_name_a_document_only_from_three_questions(client, db_session, monkeypatch, organization):
    often = _readable(db_session, organization, "Regulamento de ferias")
    once = _readable(db_session, organization, "Licenca parental")
    for _ in range(3):
        _ask(client, monkeypatch, organization, _no_answer(often))
    _ask(client, monkeypatch, organization, _no_answer(once, issues=[NOT_RELEVANT]))
    _ask(client, monkeypatch, organization, _no_answer())
    # An answer is not a gap, and records no consulted documents.
    _ask(client, monkeypatch, organization, _result(document_id=often))

    body = _gaps(client, organization)
    assert body["unanswered"] == 5
    assert body["reasons"] == {"no_sources": 1, "not_found": 3, "checks": 0, "not_relevant": 1}
    assert body["documents"] == [
        {"document_id": str(often), "title": "Regulamento de ferias", "questions": 3}
    ]
    assert body["hidden_documents"] == 0 and body["min_questions"] == 3
    answered = db_session.query(AnswerEvent).filter_by(abstained=False).one()
    assert answered.consulted_document_ids == [] and answered.gap_reason is None


def test_gap_documents_the_viewer_cannot_open_are_only_counted(client, monkeypatch, organization):
    hidden = uuid.uuid4()
    for _ in range(3):
        _ask(client, monkeypatch, organization, _no_answer(hidden))
    body = _gaps(client, organization)
    assert body["documents"] == [] and body["hidden_documents"] == 1


def test_gaps_are_empty_without_unanswered_questions(client, monkeypatch, organization):
    _ask(client, monkeypatch, organization)
    body = _gaps(client, organization)
    assert body["unanswered"] == 0 and body["documents"] == []
    assert set(body["reasons"]) == {"no_sources", "not_found", "checks", "not_relevant"}


def test_gaps_of_another_organization_are_refused(client):
    response = client.get(f"/api/v1/organizations/{uuid.uuid4()}/dashboard/gaps")
    assert response.status_code in (403, 404)
