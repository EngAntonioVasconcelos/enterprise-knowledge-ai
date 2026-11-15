import uuid
from urllib.parse import parse_qs

import httpx
import pytest
from sqlalchemy import select

from app.connectors import google_drive
from app.core.config import settings
from app.models.data_connection import DataConnection
from app.models.document import Document, DocumentVersion
from app.models.document_access import DocumentPermission
from app.services import sync_service
from app.services.sync_service import sync_connection
from app.services.text_extraction import MAX_FILE_BYTES
from tests.test_text_extraction import make_pdf


DOC = google_drive.GOOGLE_DOC
PDF = "application/pdf"
ACCOUNT = "drive.owner@example.com"


class FakeDrive:
    """Google sign-in and the Drive API in memory."""

    def __init__(self):
        self.files: dict[str, dict] = {}
        self.content: dict[str, bytes] = {}
        self.shared_permissions: dict[str, list] = {}
        self.changes: list[dict] = []
        self.start_token = "100"
        self.incomplete = False
        self.revoked = False
        self.expire_next = False
        self.busy: set[str] = set()
        self.refreshes = 0
        self.requests: list[httpx.Request] = []
        self.closed = 0

    def add(self, file_id, name, mime, text=None, data=None, **extra):
        self.files[file_id] = {
            "id": file_id,
            "name": name,
            "mimeType": mime,
            "version": "1",
            "modifiedTime": "2026-11-01T10:00:00.000Z",
            **extra,
        }
        self.content[file_id] = data if data is not None else text.encode("utf-8")

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        path = request.url.path
        params = dict(request.url.params)

        if url.startswith(google_drive.TOKEN_URL):
            form = parse_qs(request.content.decode())
            assert form["client_secret"] == ["test-client-secret"]
            if self.revoked:
                return httpx.Response(400, json={"error": "invalid_grant"})
            self.refreshes += 1
            return httpx.Response(200, json={"access_token": f"at-{self.refreshes}"})

        token = request.headers.get("Authorization", "")
        if self.expire_next:
            self.expire_next = False
            return httpx.Response(401, json={"error": {"status": "UNAUTHENTICATED"}})
        assert token == f"Bearer at-{self.refreshes}"

        path = path.removeprefix("/drive/v3")
        if path == "/about":
            return httpx.Response(200, json={"user": {"emailAddress": ACCOUNT}})
        if path == "/changes/startPageToken":
            return httpx.Response(200, json={"startPageToken": self.start_token})
        if path == "/files":
            return httpx.Response(
                200,
                json={
                    "files": list(self.files.values()),
                    "incompleteSearch": self.incomplete,
                },
            )
        if path == "/changes":
            assert params["pageToken"]
            changes, self.changes = self.changes, []
            return httpx.Response(
                200, json={"changes": changes, "newStartPageToken": "200"}
            )

        parts = path.split("/")
        file_id = parts[2]
        if file_id in self.busy:
            return httpx.Response(429, json={"error": {"errors": [{"reason": "rateLimitExceeded"}]}})
        if path.endswith("/permissions"):
            return httpx.Response(
                200, json={"permissions": self.shared_permissions[file_id]}
            )
        if path.endswith("/export"):
            assert params["mimeType"] == "text/plain"
            return httpx.Response(200, content=b"\xef\xbb\xbf" + self.content[file_id])
        if params.get("alt") == "media":
            return httpx.Response(200, content=self.content[file_id])
        raise AssertionError(f"unexpected request {request.method} {url}")

    def client(self):
        drive = self

        class Client(httpx.Client):
            def close(self):
                drive.closed += 1
                super().close()

        return Client(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def drive(monkeypatch, tmp_path):
    fake = FakeDrive()
    monkeypatch.setattr(google_drive, "http_client", fake.client)
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    fake.credentials = {"refresh_token": "test-refresh-token"}
    monkeypatch.setattr(
        sync_service, "_credentials", lambda db, connection: fake.credentials
    )
    return fake


@pytest.fixture
def connection(client, db_session):
    unique = uuid.uuid4().hex[:8]
    organization = client.post(
        "/api/v1/organizations/",
        json={"name": f"Drive Org {unique}", "slug": f"drive-{unique}"},
    ).json()
    created = client.post(
        f"/api/v1/organizations/{organization['id']}/connections/",
        json={"provider": "google_drive", "name": "Company Drive"},
    ).json()
    return db_session.get(DataConnection, uuid.UUID(created["id"]))


def _sync(db, connection):
    summary = sync_connection(db, connection_id=connection.id)
    db.commit()
    db.expire_all()
    return summary


def _documents(db, connection):
    return {
        d.external_id: d
        for d in db.scalars(
            select(Document).where(Document.connection_id == connection.id)
        )
    }


def _text(db, document):
    version = db.get(DocumentVersion, document.current_version_id)
    from app.services.object_storage import get_object_storage

    return get_object_storage().get(version.normalized_object_key).decode()


def _permissions(db, document):
    return {
        (p.principal_type, p.principal, p.role)
        for p in db.scalars(
            select(DocumentPermission).where(
                DocumentPermission.document_id == document.id
            )
        )
    }


def test_the_first_sync_reads_every_supported_file(db_session, connection, drive):
    drive.add(
        "d1",
        "Vacation policy",
        DOC,
        "Employees get 22 days.",
        permissions=[
            {"type": "user", "role": "owner", "emailAddress": "Ana@Example.com"},
            {"type": "domain", "role": "reader", "domain": "example.com"},
            {"type": "user", "role": "writer", "emailAddress": "gone@example.com", "deleted": True},
            {"type": "user", "role": "someNewRole", "emailAddress": "x@example.com"},
        ],
    )
    drive.add(
        "p1",
        "Handbook.pdf",
        PDF,
        data=make_pdf("Welcome to the company"),
        md5Checksum="abc123",
        size="900",
        permissions=[{"type": "anyone", "role": "reader"}],
    )

    summary = _sync(db_session, connection)

    assert summary["new_version"] == 2 and summary["failed"] == 0
    documents = _documents(db_session, connection)
    assert _text(db_session, documents["d1"]) == "Employees get 22 days."
    assert "Welcome to the company" in _text(db_session, documents["p1"])
    assert _permissions(db_session, documents["d1"]) == {
        ("user", "ana@example.com", "owner"),
        ("domain", "example.com", "reader"),
    }
    assert _permissions(db_session, documents["p1"]) == {("anyone", "", "reader")}

    connection = db_session.get(DataConnection, connection.id)
    assert (connection.sync_cursor, connection.status) == ("100", "active")
    listing = next(r for r in drive.requests if r.url.path.endswith("/files"))
    query = listing.url.params["q"]
    assert "trashed = false" in query and DOC in query
    assert "spreadsheet" not in query
    # The network client is released when the sync ends.
    assert drive.closed == 1


def test_unknown_sharing_grants_only_the_connected_account(
    db_session, connection, drive
):
    drive.add("d1", "Shared with me", DOC, "Read only for us.")
    drive.add("s1", "Team drive file", DOC, "In a shared drive.", driveId="team-1")
    drive.shared_permissions["s1"] = [
        {"type": "group", "role": "organizer", "emailAddress": "team@example.com"},
    ]

    _sync(db_session, connection)

    documents = _documents(db_session, connection)
    assert _permissions(db_session, documents["d1"]) == {
        ("user", ACCOUNT, "reader")
    }
    assert _permissions(db_session, documents["s1"]) == {
        ("group", "team@example.com", "writer")
    }


def test_later_syncs_read_only_the_changes(db_session, connection, drive):
    for file_id in ("d1", "d2", "d3", "d4", "d5"):
        drive.add(file_id, f"Doc {file_id}", DOC, f"Text of {file_id}.",
                  permissions=[{"type": "anyone", "role": "reader"}])
    _sync(db_session, connection)

    changed = dict(drive.files["d1"], version="2")
    drive.content["d1"] = b"New text of d1."
    drive.changes = [
        {"changeType": "file", "fileId": "d1", "file": changed},
        {"changeType": "file", "fileId": "d2", "removed": True},
        {"changeType": "file", "fileId": "d3", "file": dict(drive.files["d3"], trashed=True)},
        {"changeType": "file", "fileId": "d4", "file": dict(drive.files["d4"], mimeType="image/png")},
        {"changeType": "drive", "driveId": "team-1"},
    ]
    drive.requests.clear()

    summary = _sync(db_session, connection)

    assert (summary["new_version"], summary["removed"]) == (1, 3)
    documents = _documents(db_session, connection)
    assert _text(db_session, documents["d1"]) == "New text of d1."
    assert {k: d.status for k, d in documents.items()} == {
        "d1": "active",
        "d2": "removed",
        "d3": "removed",
        "d4": "removed",
        # Not in the changes, so not touched: an incremental sync never
        # removes what it did not hear about.
        "d5": "active",
    }
    assert not any(r.url.path.endswith("/files") for r in drive.requests)
    assert db_session.get(DataConnection, connection.id).sync_cursor == "200"


def test_an_expired_access_token_is_refreshed_once(db_session, connection, drive):
    drive.add("d1", "Doc", DOC, "Text.", permissions=[])
    _sync(db_session, connection)
    drive.expire_next = True
    drive.changes = [
        {"changeType": "file", "fileId": "d1", "file": dict(drive.files["d1"], version="2")}
    ]
    drive.content["d1"] = b"Changed."

    summary = _sync(db_session, connection)

    assert summary["new_version"] == 1
    # One sign-in per sync, plus one when the access token expired.
    assert drive.refreshes == 3


def test_a_revoked_authorization_puts_the_connection_in_error(
    db_session, connection, drive
):
    drive.add("d1", "Doc", DOC, "Text.", permissions=[])
    _sync(db_session, connection)
    drive.revoked = True

    _sync(db_session, connection)

    connection = db_session.get(DataConnection, connection.id)
    assert connection.status == "error"
    assert "invalid_grant" in connection.last_error
    # The refresh token never reaches the error message.
    assert "test-refresh-token" not in connection.last_error
    assert _documents(db_session, connection)["d1"].status == "active"


def test_a_connection_without_authorization_is_put_in_error(
    db_session, connection, drive
):
    drive.credentials = None

    _sync(db_session, connection)

    connection = db_session.get(DataConnection, connection.id)
    assert connection.status == "error"
    assert "connect the account again" in connection.last_error


def test_a_busy_drive_stops_the_sync_and_keeps_the_cursor(
    db_session, connection, drive
):
    drive.add("d1", "Doc 1", DOC, "One.", permissions=[])
    drive.add("d2", "Doc 2", DOC, "Two.", permissions=[])
    drive.busy = {"d1"}

    summary = _sync(db_session, connection)

    assert summary["failed"] == 1
    connection = db_session.get(DataConnection, connection.id)
    # Nothing was learned for sure: the next run lists everything again.
    assert connection.sync_cursor is None
    assert "d1" in connection.last_error

    drive.busy = set()
    summary = _sync(db_session, connection)
    assert summary["new_version"] == 2
    assert db_session.get(DataConnection, connection.id).sync_cursor == "100"


def test_one_unreadable_file_does_not_hold_the_others(db_session, connection, drive):
    drive.add("big", "Huge.pdf", PDF, data=b"%PDF-", size=str(MAX_FILE_BYTES + 1))
    drive.add("d1", "Doc", DOC, "Fine.", permissions=[])

    summary = _sync(db_session, connection)

    assert (summary["new_version"], summary["failed"]) == (1, 1)
    # A file that cannot be read is not a reason to read everything again.
    assert db_session.get(DataConnection, connection.id).sync_cursor == "100"
    # The large file was never downloaded.
    assert not any(
        r.url.params.get("alt") == "media" for r in drive.requests
    )


def test_an_incomplete_listing_removes_nothing(db_session, connection, drive):
    drive.add("d1", "Doc 1", DOC, "One.", permissions=[])
    drive.add("d2", "Doc 2", DOC, "Two.", permissions=[])
    _sync(db_session, connection)
    connection = db_session.get(DataConnection, connection.id)
    connection.sync_cursor = None
    db_session.commit()

    del drive.files["d2"]
    drive.incomplete = True
    _sync(db_session, connection)

    assert _documents(db_session, connection)["d2"].status == "active"


def test_the_refresh_token_never_appears_in_a_repr(drive):
    client = google_drive.DriveClient("test-refresh-token", drive.client())
    assert "test-refresh-token" not in repr(client)
