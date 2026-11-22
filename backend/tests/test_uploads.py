import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.document import Document, DocumentVersion
from app.models.document_access import DocumentPermission
from app.models.file_upload import FileUpload
from app.models.membership import OrganizationMembership
from app.models.user import User
from app.services import text_extraction
from app.services.worker import run_once
from tests.conftest import test_engine
from tests.test_text_extraction import make_docx, make_pdf


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    return tmp_path


@pytest.fixture
def uploads_url(client):
    unique = uuid.uuid4().hex[:8]
    organization = client.post(
        "/api/v1/organizations/",
        json={"name": f"Upload Org {unique}", "slug": f"upload-{unique}"},
    ).json()
    connection = client.post(
        f"/api/v1/organizations/{organization['id']}/connections/",
        json={"provider": "file_upload", "name": "Uploads"},
    ).json()
    return (
        f"/api/v1/organizations/{organization['id']}/connections/"
        f"{connection['id']}/uploads"
    )


def _upload(client, url, name, data, visibility=None):
    form = {"visibility": visibility} if visibility else {}
    return client.post(f"{url}/", files={"file": (name, data)}, data=form)


def _sync():
    return run_once(test_engine, worker_id="test", assume_role=None, limit=5)


def test_an_uploaded_pdf_becomes_a_document_after_the_sync(
    client, db_session, uploads_url
):
    response = _upload(
        client, uploads_url, "Vacation policy.pdf", make_pdf("22 days")
    )
    assert response.status_code == 201
    body = response.json()
    assert (body["filename"], body["mime_type"]) == (
        "Vacation policy.pdf",
        "application/pdf",
    )

    assert _sync()["succeeded"] == 1

    db_session.expire_all()
    document = db_session.scalars(select(Document)).one()
    version = db_session.get(DocumentVersion, document.current_version_id)
    assert (document.title, document.status) == ("Vacation policy.pdf", "active")
    assert version.source_revision == db_session.get(
        FileUpload, uuid.UUID(body["id"])
    ).sha256
    permission = db_session.scalars(select(DocumentPermission)).one()
    assert permission.principal_type == "organization"


def test_only_me_becomes_a_permission_for_the_uploader_alone(
    client, db_session, uploads_url, authenticated_user
):
    _upload(
        client,
        uploads_url,
        "Notes.docx",
        make_docx(["my notes"]),
        visibility="private",
    )
    _sync()

    db_session.expire_all()
    permission = db_session.scalars(select(DocumentPermission)).one()
    assert (permission.principal_type, permission.principal) == (
        "user",
        authenticated_user.email,
    )


def test_unchanged_uploads_are_not_read_again(
    client, db_session, uploads_url, monkeypatch
):
    _upload(client, uploads_url, "a.txt", b"first file")
    _sync()

    reads = []
    original = text_extraction.extract_text
    monkeypatch.setattr(
        "app.connectors.file_upload.extract_text",
        lambda data: reads.append(1) or original(data),
    )
    _upload(client, uploads_url, "b.txt", b"second file")
    _sync()

    # Only the new file was opened and parsed.
    assert reads == [1]
    db_session.expire_all()
    assert len(db_session.scalars(select(Document)).all()) == 2


def test_deleting_an_upload_takes_it_out_of_retrieval(
    client, db_session, uploads_url
):
    upload = _upload(client, uploads_url, "a.txt", b"some text").json()
    _sync()

    assert client.delete(f"{uploads_url}/{upload['id']}").status_code == 204
    assert client.get(f"{uploads_url}/").json() == []
    _sync()

    db_session.expire_all()
    assert db_session.scalars(select(Document)).one().status == "removed"
    assert client.delete(f"{uploads_url}/{upload['id']}").status_code == 404


def test_bad_files_are_refused_before_storage(client, uploads_url, storage):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    assert _upload(client, uploads_url, "photo.pdf", png).status_code == 415
    assert _upload(client, uploads_url, "empty.txt", b"").status_code == 415
    assert (
        _upload(client, uploads_url, "a.txt", b"x", visibility="world")
        .status_code
        == 400
    )
    assert list(storage.rglob("original")) == []


def test_files_over_the_limit_are_refused(client, uploads_url, monkeypatch):
    monkeypatch.setattr("app.api.routes.uploads.MAX_FILE_BYTES", 10)

    response = _upload(client, uploads_url, "big.txt", b"x" * 11)

    assert response.status_code == 413


def test_a_file_that_cannot_be_read_does_not_stop_the_others(
    client, db_session, uploads_url
):
    _upload(client, uploads_url, "scan.pdf", make_pdf(""))
    _upload(client, uploads_url, "ok.txt", b"readable")
    _sync()

    db_session.expire_all()
    assert [d.title for d in db_session.scalars(select(Document))] == ["ok.txt"]


def test_viewers_cannot_upload_and_names_stay_private(
    client, client_for_user, db_session, uploads_url
):
    organization_id = uploads_url.split("/")[4]
    viewer = User(
        email=f"viewer-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Viewer",
        is_active=True,
    )
    db_session.add(viewer)
    db_session.flush()
    db_session.add(
        OrganizationMembership(
            organization_id=uuid.UUID(organization_id),
            user_id=viewer.id,
            role="viewer",
            is_active=True,
        )
    )
    db_session.commit()

    with client_for_user(viewer) as other:
        assert _upload(other, uploads_url, "a.txt", b"x").status_code == 403


def test_uploads_need_an_upload_connection(client):
    unique = uuid.uuid4().hex[:8]
    organization = client.post(
        "/api/v1/organizations/",
        json={"name": f"Drive Org {unique}", "slug": f"drive-{unique}"},
    ).json()
    drive = client.post(
        f"/api/v1/organizations/{organization['id']}/connections/",
        json={"provider": "google_drive", "name": "Drive"},
    ).json()
    url = (
        f"/api/v1/organizations/{organization['id']}/connections/"
        f"{drive['id']}/uploads"
    )

    assert _upload(client, url, "a.txt", b"x").status_code == 400


def _member(db_session, organization_id, role):
    person = User(
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.com",
        full_name=role.title(),
        is_active=True,
    )
    db_session.add(person)
    db_session.flush()
    db_session.add(
        OrganizationMembership(
            organization_id=uuid.UUID(organization_id),
            user_id=person.id,
            role=role,
            is_active=True,
        )
    )
    db_session.commit()
    return person


def test_members_find_the_upload_source_and_viewers_do_not(
    client, client_for_user, db_session, uploads_url
):
    organization_id, connection_id = uploads_url.split("/")[4], uploads_url.split("/")[6]
    url = f"/api/v1/organizations/{organization_id}/upload-source"

    with client_for_user(_member(db_session, organization_id, "member")) as member:
        response = member.get(url)
        assert response.status_code == 200
        assert response.json()["id"] == connection_id
        # Finding it lets a member upload, without listing connections.
        assert member.get(f"/api/v1/organizations/{organization_id}/connections/").status_code == 403
        assert _upload(member, uploads_url, "mine.txt", b"x", "private").status_code == 201

    with client_for_user(_member(db_session, organization_id, "viewer")) as viewer:
        assert viewer.get(url).status_code == 403


def test_no_upload_source_yet_is_said_plainly(client):
    unique = uuid.uuid4().hex[:8]
    organization = client.post(
        "/api/v1/organizations/",
        json={"name": f"Empty Org {unique}", "slug": f"empty-{unique}"},
    ).json()
    response = client.get(f"/api/v1/organizations/{organization['id']}/upload-source")
    assert response.status_code == 404
