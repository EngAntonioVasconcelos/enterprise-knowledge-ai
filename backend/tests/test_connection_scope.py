import uuid

import pytest
from sqlalchemy import select

from app.connectors.base import CONNECTORS, ChangeSet, SourceItem
from app.core.config import settings
from app.models.data_connection import DataConnection
from app.models.document import Document
from app.services.connection_scope import (
    allowed_mime_types,
    file_types_fingerprint,
    validate_scope,
)
from app.services.document_permission_service import SourcePermission
from app.services.sync_service import sync_connection
from tests.test_text_extraction import make_pdf


PDF = "application/pdf"
TEXT = "text/plain"


class MixedSource:
    """A source with PDFs and text files that remembers the cursors it got."""

    def __init__(self):
        self.items = {"p1": PDF, "t1": TEXT}
        self.cursors = []

    def connector(self, context):
        source = self

        class Connector:
            def list_changes(self, cursor):
                source.cursors.append(cursor)
                return ChangeSet(
                    changed=tuple(
                        SourceItem(
                            external_id=external_id,
                            title=external_id,
                            mime_type=mime,
                            revision="1",
                            permissions=(SourcePermission("organization"),),
                        )
                        for external_id, mime in source.items.items()
                    ),
                    cursor="token-1",
                )

            def fetch_text(self, item):
                return f"Text of {item.external_id}."

        return Connector()


@pytest.fixture
def source(monkeypatch, tmp_path):
    fake = MixedSource()
    monkeypatch.setitem(CONNECTORS, "file_upload", fake.connector)
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    return fake


@pytest.fixture
def organization(client):
    unique = uuid.uuid4().hex[:8]
    return client.post(
        "/api/v1/organizations/",
        json={"name": f"Scope Org {unique}", "slug": f"scope-{unique}"},
    ).json()["id"]


def _connection(client, organization, settings_=None):
    response = client.post(
        f"/api/v1/organizations/{organization}/connections/",
        json={"provider": "file_upload", "name": "Files", "settings": settings_ or {}},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _set_scope(client, organization, connection_id, scope):
    response = client.patch(
        f"/api/v1/organizations/{organization}/connections/{connection_id}",
        json={"settings": {} if scope is None else {"scope": scope}},
    )
    assert response.status_code == 200, response.text


def _sync(db, connection_id):
    summary = sync_connection(db, connection_id=uuid.UUID(connection_id))
    db.commit()
    db.expire_all()
    return summary


def _active(db, connection_id):
    return sorted(
        d.external_id
        for d in db.scalars(
            select(Document).where(
                Document.connection_id == uuid.UUID(connection_id),
                Document.status == "active",
            )
        )
    )


# The rules


@pytest.mark.parametrize(
    "scope",
    [
        {"roles": []},
        {"roles": ["superuser"]},
        {"roles": ["member", "member"]},
        {"file_types": ["exe"]},
        {"file_types": "pdf"},
        {"teams": ["finance"]},
        ["member"],
    ],
)
def test_malformed_scopes_are_refused(client, organization, scope):
    response = client.post(
        f"/api/v1/organizations/{organization}/connections/",
        json={"provider": "file_upload", "name": "Files", "settings": {"scope": scope}},
    )

    assert response.status_code == 422


def test_a_well_formed_scope_is_kept(client, organization):
    scope = {"roles": ["owner", "admin"], "file_types": ["pdf", "google_docs"]}
    connection_id = _connection(client, organization, {"scope": scope})

    response = client.get(
        f"/api/v1/organizations/{organization}/connections/{connection_id}"
    )

    assert response.json()["settings"]["scope"] == scope
    assert validate_scope(scope) == scope


def test_file_types_become_mime_types():
    assert allowed_mime_types({}) is None
    assert allowed_mime_types({"scope": {"roles": ["member"]}}) is None
    assert allowed_mime_types({"scope": {"file_types": ["pdf", "text"]}}) == {
        PDF,
        TEXT,
        "text/markdown",
    }
    assert file_types_fingerprint(
        {"scope": {"file_types": ["pdf", "text"]}}
    ) == file_types_fingerprint({"scope": {"file_types": ["text", "pdf"]}})


# File types in the sync engine


def test_excluded_file_types_are_not_read(client, db_session, organization, source):
    connection_id = _connection(
        client, organization, {"scope": {"file_types": ["pdf"]}}
    )

    summary = _sync(db_session, connection_id)

    assert summary["new_version"] == 1
    assert _active(db_session, connection_id) == ["p1"]


def test_changing_the_filter_lists_everything_again(
    client, db_session, organization, source
):
    connection_id = _connection(client, organization)
    _sync(db_session, connection_id)
    assert _active(db_session, connection_id) == ["p1", "t1"]
    assert source.cursors == [None]

    # Narrowing removes what is now excluded.
    _set_scope(client, organization, connection_id, {"file_types": ["pdf"]})
    _sync(db_session, connection_id)
    assert _active(db_session, connection_id) == ["p1"]

    # The same filter continues from the saved position.
    _sync(db_session, connection_id)

    # Lifting it brings the text file back.
    _set_scope(client, organization, connection_id, None)
    _sync(db_session, connection_id)
    assert _active(db_session, connection_id) == ["p1", "t1"]

    assert source.cursors == [None, None, "token-1", None]
    cursor = db_session.get(DataConnection, uuid.UUID(connection_id)).sync_cursor
    assert cursor == "token-1"


# Uploads


def _uploads_url(organization, connection_id):
    return f"/api/v1/organizations/{organization}/connections/{connection_id}/uploads/"


def test_an_upload_outside_the_roles_of_the_scope_is_refused(
    client, organization, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    # The test user owns the organization; the connection is for members.
    connection_id = _connection(client, organization, {"scope": {"roles": ["member"]}})

    response = client.post(
        _uploads_url(organization, connection_id),
        files={"file": ("notes.txt", b"Some notes.")},
    )

    assert response.status_code == 403


def test_an_upload_of_an_excluded_type_is_refused(
    client, organization, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    connection_id = _connection(client, organization, {"scope": {"file_types": ["pdf"]}})

    refused = client.post(
        _uploads_url(organization, connection_id),
        files={"file": ("notes.txt", b"Some notes.")},
    )
    accepted = client.post(
        _uploads_url(organization, connection_id),
        files={"file": ("report.pdf", make_pdf("Quarterly report"))},
    )

    assert refused.status_code == 415
    assert accepted.status_code == 201
