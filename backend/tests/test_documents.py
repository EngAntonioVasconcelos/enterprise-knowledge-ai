import uuid

import pytest

from app.models.data_connection import DataConnection
from app.services import document_service as documents
from app.services.document_service import (
    DocumentVersionError,
    content_hash,
    normalize_content,
)


@pytest.fixture
def connection(client, db_session):
    unique = uuid.uuid4().hex[:8]
    organization = client.post(
        "/api/v1/organizations/",
        json={"name": f"Docs Org {unique}", "slug": f"docs-{unique}"},
    ).json()
    created = client.post(
        f"/api/v1/organizations/{organization['id']}/connections/",
        json={"provider": "google_drive", "name": "Drive"},
    ).json()
    return db_session.get(DataConnection, uuid.UUID(created["id"]))


def _document(db, connection, external_id="file-1", title="Policy"):
    return documents.upsert_document(
        db,
        organization_id=connection.organization_id,
        connection_id=connection.id,
        external_id=external_id,
        title=title,
    )


def _version(db, document, text):
    return documents.add_version(
        db,
        document=document,
        content_hash=content_hash(normalize_content(text)),
        size_bytes=len(text),
    )


def test_normalization_ignores_layout_but_not_meaning():
    a = "Vacation policy\r\n\r\n\r\n\r\nEmployees get 22 days.   \n"
    b = "Vacation policy\n\nEmployees get 22 days."
    c = "Vacation policy\n\nEmployees get 25 days."

    assert normalize_content(a) == normalize_content(b)
    assert content_hash(normalize_content(a)) == content_hash(
        normalize_content(b)
    )
    assert content_hash(normalize_content(b)) != content_hash(
        normalize_content(c)
    )
    # Composed and decomposed accents are the same text.
    assert normalize_content("Fe\u0301rias") == normalize_content("F\u00e9rias")


def test_a_source_item_has_one_document(db_session, connection):
    first = _document(db_session, connection)
    again = _document(db_session, connection, title="Policy v2")

    assert again.id == first.id
    assert again.title == "Policy v2"
    assert again.status == "pending"


def test_unchanged_content_creates_no_new_version(db_session, connection):
    document = _document(db_session, connection)
    version = _version(db_session, document, "Employees get 22 days.")
    documents.mark_version_ready(db_session, version)
    documents.activate_version(db_session, document=document, version=version)

    assert _version(db_session, document, "Employees get 22 days.\n\n") is None

    changed = _version(db_session, document, "Employees get 25 days.")
    assert changed.version_number == 2


def test_a_new_version_becomes_current_only_when_ready(db_session, connection):
    document = _document(db_session, connection)
    first = _version(db_session, document, "v1")
    documents.mark_version_ready(db_session, first)
    documents.activate_version(db_session, document=document, version=first)

    second = _version(db_session, document, "v2")
    with pytest.raises(DocumentVersionError):
        documents.activate_version(
            db_session, document=document, version=second
        )

    # Processing fails: the previous version stays current.
    documents.fail_version(db_session, second, error="parser crashed")
    assert document.current_version_id == first.id
    assert document.status == "active"

    with pytest.raises(DocumentVersionError):
        documents.mark_version_ready(db_session, second)


def test_a_first_version_that_fails_marks_the_document_failed(
    db_session, connection
):
    document = _document(db_session, connection)
    version = _version(db_session, document, "v1")

    documents.fail_version(db_session, version, error="unsupported format")

    assert document.status == "failed"
    assert document.current_version_id is None


def test_a_version_of_another_document_cannot_become_current(
    db_session, connection
):
    first = _document(db_session, connection, external_id="a")
    second = _document(db_session, connection, external_id="b")
    version = _version(db_session, first, "content")
    documents.mark_version_ready(db_session, version)

    with pytest.raises(DocumentVersionError):
        documents.activate_version(
            db_session, document=second, version=version
        )


def test_removing_takes_a_document_out_and_keeps_its_versions(
    db_session, connection
):
    document = _document(db_session, connection)
    version = _version(db_session, document, "content")
    documents.mark_version_ready(db_session, version)
    documents.activate_version(db_session, document=document, version=version)

    documents.remove_document(db_session, document=document)

    assert document.status == "removed"
    assert document.removed_at is not None
    assert documents.current_version(db_session, document).id == version.id
