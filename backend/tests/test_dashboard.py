import uuid

import pytest

from app.models import AnswerEvent, Document
from tests.test_history import _ask, _result


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
