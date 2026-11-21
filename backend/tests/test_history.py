import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.api.routes import answers
from app.models import Document, QuestionHistory
from app.services.answer_service import Source
from app.services.search_service import SearchHit


DOCUMENT = uuid.uuid4()
VERSION = uuid.uuid4()


def _hit(document_id, version_id, title):
    return SearchHit(
        chunk_id=uuid.uuid4(),
        document_id=document_id,
        version_id=version_id,
        title=title,
        heading=None,
        snippet="Cada colaborador tem 25 dias uteis.",
        start_char=0,
        end_char=34,
        score=1.0,
        content="Cada colaborador tem 25 dias uteis.",
    )


def _result(document_id=DOCUMENT, version_id=VERSION):
    return SimpleNamespace(
        answer="Tens 25 dias uteis [1].",
        abstained=False,
        verified=True,
        language="pt",
        cited=[1],
        sources=[
            Source(1, _hit(document_id, version_id, "Manual")),
            Source(2, _hit(uuid.uuid4(), uuid.uuid4(), "Outro")),
        ],
        prompt_id="answer_v3",
        model="test",
        note=None,
        timings_ms={"search": 1.0},
    )


@pytest.fixture
def organization(client):
    return client.post(
        "/api/v1/organizations/",
        json={"name": "History Org", "slug": f"history-{uuid.uuid4().hex[:8]}"},
    ).json()


def _ask(client, monkeypatch, organization, result=None):
    monkeypatch.setattr(
        answers, "answer_question", lambda db, **kwargs: result or _result()
    )
    response = client.post(
        f"/api/v1/organizations/{organization['id']}/answers/",
        json={"question": "Quantos dias de ferias tenho?"},
    )
    assert response.status_code == 200, response.text
    return response


def _document(db, organization, *, version=VERSION, status="active"):
    db.add(
        Document(
            id=DOCUMENT,
            organization_id=uuid.UUID(organization["id"]),
            connection_id=uuid.uuid4(),
            external_id="manual",
            title="Manual",
            status=status,
            current_version_id=version,
        )
    )
    db.flush()


def _base(organization):
    return f"/api/v1/organizations/{organization['id']}/history/"


def test_an_answer_is_kept_and_opened_again(client, db_session, monkeypatch, organization):
    _document(db_session, organization)
    _ask(client, monkeypatch, organization)

    items = client.get(_base(organization)).json()
    assert [item["question"] for item in items] == ["Quantos dias de ferias tenho?"]

    entry = client.get(_base(organization) + items[0]["id"]).json()
    assert entry["answer"] == "Tens 25 dias uteis [1]." and not entry["hidden"]
    assert not entry["outdated"]
    # The consulted source whose document is gone is not shown again.
    assert [source["title"] for source in entry["sources"]] == ["Manual"]


def test_the_answer_is_hidden_when_a_cited_document_is_gone(
    client, db_session, monkeypatch, organization
):
    _document(db_session, organization, status="removed")
    _ask(client, monkeypatch, organization)
    item = client.get(_base(organization)).json()[0]

    entry = client.get(_base(organization) + item["id"]).json()
    assert entry["hidden"] and entry["answer"] is None and entry["sources"] == []


def test_a_newer_version_is_flagged(client, db_session, monkeypatch, organization):
    _document(db_session, organization, version=uuid.uuid4())
    _ask(client, monkeypatch, organization)
    item = client.get(_base(organization)).json()[0]

    entry = client.get(_base(organization) + item["id"]).json()
    assert entry["outdated"] and entry["answer"]


def test_nothing_is_kept_when_the_organization_keeps_no_history(
    client, monkeypatch, organization
):
    updated = client.patch(
        f"/api/v1/organizations/{organization['id']}",
        json={"history_retention_days": 0},
    )
    assert updated.status_code == 200 and updated.json()["history_retention_days"] == 0
    _ask(client, monkeypatch, organization)
    assert client.get(_base(organization)).json() == []


def test_only_known_retention_periods_are_accepted(client, organization):
    refused = client.patch(
        f"/api/v1/organizations/{organization['id']}",
        json={"history_retention_days": 7},
    )
    assert refused.status_code == 422
    listed = client.get("/api/v1/organizations/").json()
    assert listed[0]["history_retention_days"] == 90


def test_expired_entries_are_not_listed(client, db_session, monkeypatch, organization):
    _ask(client, monkeypatch, organization)
    entry = db_session.query(QuestionHistory).one()
    entry.created_at = datetime.now(timezone.utc) - timedelta(days=91)
    db_session.flush()

    assert client.get(_base(organization)).json() == []
    assert client.get(_base(organization) + str(entry.id)).status_code == 404


def test_entries_are_deleted_one_or_all(client, monkeypatch, organization):
    _ask(client, monkeypatch, organization)
    _ask(client, monkeypatch, organization)
    first, second = client.get(_base(organization)).json()

    assert client.delete(_base(organization) + first["id"]).status_code == 204
    assert client.delete(_base(organization) + first["id"]).status_code == 404
    assert [item["id"] for item in client.get(_base(organization)).json()] == [second["id"]]
    assert client.delete(_base(organization)).status_code == 204
    assert client.get(_base(organization)).json() == []


def test_another_organization_is_refused(client):
    other = f"/api/v1/organizations/{uuid.uuid4()}/history/"
    assert client.get(other).status_code in (403, 404)
