"""Connect a Google Drive account to a connection (OAuth 2.0 with PKCE).

1. An Owner or Admin asks for the authorization address. Its "state" is
   signed by the server and names the organization, the connection, the
   person and an expiry (10 minutes), so a callback cannot be replayed
   into another connection or by another person.
2. Google sends the browser back to the frontend with a one-time code;
   the frontend posts code and state here.
3. The server exchanges the code (with the PKCE verifier, derived from the
   state, so nothing has to be stored in between) and seals the refresh
   token at once (ADR-007). Nothing about the token is ever returned.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import DomainError, InvalidInputError
from app.models.data_connection import DataConnection
from app.services.connection_service import ConnectionDisconnectedError
from app.services.credential_service import store_credentials


AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
STATE_TTL_SECONDS = 600


class GoogleOAuthNotConfiguredError(DomainError):
    status_code = 503


class InvalidOAuthStateError(InvalidInputError):
    pass


class GoogleAuthorizationError(InvalidInputError):
    pass


def http_client() -> httpx.Client:
    return httpx.Client(timeout=15.0)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _config() -> tuple[str, str, bytes, str]:
    missing = [
        name
        for name in (
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_SECRET",
            "OAUTH_STATE_SECRET",
        )
        if not getattr(settings, name)
    ]
    if missing:
        raise GoogleOAuthNotConfiguredError(
            f"Google Drive is not configured ({', '.join(missing)} not set)"
        )
    redirect = settings.GOOGLE_OAUTH_REDIRECT_URI or (
        settings.FRONTEND_BASE_URL.rstrip("/") + "/connections/google/callback"
    )
    return (
        settings.GOOGLE_OAUTH_CLIENT_ID,
        settings.GOOGLE_OAUTH_CLIENT_SECRET,
        settings.OAUTH_STATE_SECRET.encode("utf-8"),
        redirect,
    )


def _sign(key: bytes, body: bytes) -> str:
    return _b64(hmac.new(key, b"state:" + body, hashlib.sha256).digest())


def _verifier(key: bytes, nonce: str) -> str:
    # 43 characters of the allowed alphabet (RFC 7636).
    return _b64(hmac.new(key, b"pkce:" + nonce.encode("ascii"), hashlib.sha256).digest())


def _check_connection(connection: DataConnection) -> None:
    if connection.provider != "google_drive":
        raise InvalidInputError("This connection is not a Google Drive connection")
    if connection.status == "disconnected":
        raise ConnectionDisconnectedError(
            "A disconnected connection cannot be authorized"
        )


def authorization_url(
    *,
    connection: DataConnection,
    user_id: uuid.UUID,
    now: float | None = None,
) -> str:
    _check_connection(connection)
    client_id, _, key, redirect = _config()

    nonce = secrets.token_urlsafe(24)
    body = json.dumps(
        {
            "o": str(connection.organization_id),
            "c": str(connection.id),
            "u": str(user_id),
            "n": nonce,
            "e": int((now or time.time()) + STATE_TTL_SECONDS),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    state = f"{_b64(body)}.{_sign(key, body)}"
    challenge = _b64(hashlib.sha256(_verifier(key, nonce).encode("ascii")).digest())

    return AUTHORIZE_URL + "?" + urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": settings.GOOGLE_DRIVE_SCOPE,
            # A refresh token, so the worker can sync without anyone there.
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "false",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )


def _read_state(
    state: str,
    *,
    key: bytes,
    connection: DataConnection,
    user_id: uuid.UUID,
    now: float | None,
) -> str:
    invalid = InvalidOAuthStateError(
        "This authorization is not valid here; start it again"
    )
    try:
        encoded, signature = state.split(".")
        body = _unb64(encoded)
    except ValueError:
        raise invalid from None
    if not hmac.compare_digest(signature, _sign(key, body)):
        raise invalid

    data = json.loads(body)
    if (
        data.get("o") != str(connection.organization_id)
        or data.get("c") != str(connection.id)
        or data.get("u") != str(user_id)
    ):
        raise invalid
    if int(data.get("e", 0)) < (now or time.time()):
        raise InvalidOAuthStateError("This authorization expired; start it again")
    return data["n"]


def complete_authorization(
    db: Session,
    *,
    connection: DataConnection,
    user_id: uuid.UUID,
    code: str,
    state: str,
    now: float | None = None,
) -> None:
    _check_connection(connection)
    client_id, client_secret, key, redirect = _config()
    nonce = _read_state(
        state, key=key, connection=connection, user_id=user_id, now=now
    )

    try:
        with http_client() as http:
            response = http.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect,
                    "code_verifier": _verifier(key, nonce),
                },
            )
    except httpx.HTTPError:
        raise GoogleAuthorizationError("Google could not be reached; try again") from None

    if response.status_code != 200:
        try:
            reason = str(response.json().get("error", ""))
        except ValueError:
            reason = ""
        raise GoogleAuthorizationError(
            f"Google refused the authorization ({reason or response.status_code})"
        )

    tokens = response.json()
    if settings.GOOGLE_DRIVE_SCOPE not in tokens.get("scope", "").split():
        # Google lets people untick the access on its consent screen.
        raise GoogleAuthorizationError(
            "Access to Google Drive was not granted; allow it on Google's screen"
        )
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise GoogleAuthorizationError(
            "Google did not return a long-lived authorization; start again"
        )

    store_credentials(
        db,
        organization_id=connection.organization_id,
        connection_id=connection.id,
        secret={"refresh_token": refresh_token, "scope": settings.GOOGLE_DRIVE_SCOPE},
    )
    if connection.status == "error":
        # The connection failed for lack of a valid authorization; it has one now.
        connection.status = "active"
    db.flush()
