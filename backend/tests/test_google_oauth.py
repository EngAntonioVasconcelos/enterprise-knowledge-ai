import base64
import hashlib
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.core import credential_crypto as crypto
from app.core.config import settings
from app.models.data_connection import DataConnection
from app.services import google_oauth
from app.services.credential_service import load_credentials
from app.services.google_oauth import (
    InvalidOAuthStateError,
    authorization_url,
    complete_authorization,
)


SCOPE = "https://www.googleapis.com/auth/drive.readonly"


class FakeGoogle:
    def __init__(self):
        self.answer = {
            "access_token": "short-lived",
            "refresh_token": "long-lived-refresh-token",
            "scope": SCOPE,
        }
        self.status = 200
        self.forms = []

    def handler(self, request):
        assert str(request.url) == google_oauth.TOKEN_URL
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.forms.append(form)
        return httpx.Response(self.status, json=self.answer)

    def client(self):
        return httpx.Client(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def google(monkeypatch):
    fake = FakeGoogle()
    monkeypatch.setattr(google_oauth, "http_client", fake.client)
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", None)
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "http://localhost:3000")
    monkeypatch.setattr(settings, "OAUTH_STATE_SECRET", "test-state-secret-" + "x" * 40)
    return fake


@pytest.fixture
def master_private(monkeypatch):
    public, private = crypto.generate_key_pair()
    monkeypatch.setattr(
        settings, "CREDENTIALS_MASTER_PUBLIC_KEY", crypto.encode_key(public)
    )
    monkeypatch.setattr(settings, "CREDENTIALS_MASTER_PRIVATE_KEY", None)
    return private


def _connection(client, provider="google_drive"):
    unique = uuid.uuid4().hex[:8]
    organization = client.post(
        "/api/v1/organizations/",
        json={"name": f"OAuth Org {unique}", "slug": f"oauth-{unique}"},
    ).json()
    created = client.post(
        f"/api/v1/organizations/{organization['id']}/connections/",
        json={"provider": provider, "name": "Source"},
    ).json()
    base = (
        f"/api/v1/organizations/{organization['id']}/connections/"
        f"{created['id']}"
    )
    return base, uuid.UUID(created["id"])


def _start(client, base):
    response = client.post(f"{base}/google/authorize")
    assert response.status_code == 200
    url = urlparse(response.json()["authorization_url"])
    return url, {k: v[0] for k, v in parse_qs(url.query).items()}


def test_the_authorization_address_asks_google_for_drive_access(client, google):
    base, _ = _connection(client)

    url, params = _start(client, base)

    assert url.netloc == "accounts.google.com"
    assert params["client_id"] == "test-client-id"
    assert params["scope"] == SCOPE
    assert params["access_type"] == "offline"
    assert params["redirect_uri"] == "http://localhost:3000/connections/google/callback"
    assert params["code_challenge_method"] == "S256"
    assert params["state"] and params["code_challenge"]


def test_it_is_refused_when_google_is_not_configured(client, google, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", None)
    base, _ = _connection(client)

    response = client.post(f"{base}/google/authorize")

    assert response.status_code == 503
    assert "GOOGLE_OAUTH_CLIENT_SECRET" in response.json()["detail"]


def test_only_drive_connections_are_authorized_with_google(client, google):
    base, _ = _connection(client, provider="file_upload")

    assert client.post(f"{base}/google/authorize").status_code == 400


def test_the_callback_seals_the_refresh_token(
    client, db_session, google, master_private
):
    base, connection_id = _connection(client)
    _, params = _start(client, base)

    response = client.post(
        f"{base}/google/callback",
        json={"code": "one-time-code", "state": params["state"]},
    )

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert "long-lived-refresh-token" not in response.text

    [form] = google.forms
    assert form["code"] == "one-time-code"
    assert form["grant_type"] == "authorization_code"
    # The verifier sent now matches the challenge sent before (PKCE).
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(form["code_verifier"].encode()).digest()
    ).rstrip(b"=").decode()
    assert challenge == params["code_challenge"]

    connection = db_session.get(DataConnection, connection_id)
    secret = load_credentials(
        db_session,
        organization_id=connection.organization_id,
        connection_id=connection.id,
        master_private=master_private,
    )
    assert secret == {"refresh_token": "long-lived-refresh-token", "scope": SCOPE}


def test_a_connection_in_error_is_active_again_after_authorizing(
    client, db_session, google, master_private
):
    base, connection_id = _connection(client)
    connection = db_session.get(DataConnection, connection_id)
    connection.status = "error"
    db_session.commit()
    _, params = _start(client, base)

    client.post(
        f"{base}/google/callback", json={"code": "c", "state": params["state"]}
    )

    db_session.expire_all()
    assert db_session.get(DataConnection, connection_id).status == "active"


def test_a_state_does_not_work_for_another_connection(client, google, master_private):
    first, _ = _connection(client)
    second, _ = _connection(client)
    _, params = _start(client, first)

    response = client.post(
        f"{second}/google/callback", json={"code": "c", "state": params["state"]}
    )

    assert response.status_code == 400
    assert google.forms == []


def test_a_tampered_state_is_refused(client, google, master_private):
    base, _ = _connection(client)
    _, params = _start(client, base)
    body, signature = params["state"].split(".")

    for state in (body + "." + signature[::-1], "garbage", body):
        response = client.post(
            f"{base}/google/callback", json={"code": "c", "state": state}
        )
        assert response.status_code == 400
    assert google.forms == []


def test_a_state_belongs_to_the_person_who_started_it(
    client, db_session, google, master_private
):
    _, connection_id = _connection(client)
    connection = db_session.get(DataConnection, connection_id)
    state = parse_qs(
        urlparse(authorization_url(connection=connection, user_id=uuid.uuid4())).query
    )["state"][0]

    with pytest.raises(InvalidOAuthStateError):
        complete_authorization(
            db_session,
            connection=connection,
            user_id=uuid.uuid4(),
            code="c",
            state=state,
        )


def test_a_state_expires(client, db_session, google, master_private):
    _, connection_id = _connection(client)
    connection = db_session.get(DataConnection, connection_id)
    user_id = uuid.uuid4()
    state = parse_qs(
        urlparse(
            authorization_url(connection=connection, user_id=user_id, now=1_000)
        ).query
    )["state"][0]

    with pytest.raises(InvalidOAuthStateError) as error:
        complete_authorization(
            db_session,
            connection=connection,
            user_id=user_id,
            code="c",
            state=state,
            now=1_000 + google_oauth.STATE_TTL_SECONDS + 1,
        )
    assert "expired" in str(error.value)


@pytest.mark.parametrize(
    "status, answer, expected",
    [
        (400, {"error": "invalid_grant"}, "invalid_grant"),
        (200, {"refresh_token": "r", "scope": "openid"}, "not granted"),
        (200, {"access_token": "a", "scope": SCOPE}, "long-lived"),
    ],
)
def test_google_answers_that_give_no_usable_access_are_refused(
    client, google, master_private, status, answer, expected
):
    base, _ = _connection(client)
    _, params = _start(client, base)
    google.status, google.answer = status, answer

    response = client.post(
        f"{base}/google/callback", json={"code": "c", "state": params["state"]}
    )

    assert response.status_code == 400
    assert expected in response.json()["detail"]
    assert client.get(f"{base}/credentials").json()["configured"] is False


def test_the_callback_body_is_hidden_from_reprs():
    from app.schemas.google_oauth import GoogleAuthorizationCallback

    body = GoogleAuthorizationCallback(code="secret-code", state="s")
    assert "secret-code" not in repr(body) and "secret-code" not in str(body)
