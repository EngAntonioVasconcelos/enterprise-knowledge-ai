
import pytest

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jwt import InvalidTokenError
from jwt.exceptions import PyJWKClientConnectionError

from app.api.dependencies import authentication
from app.models.user import User


def create_credentials() -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="test-token",
    )


def test_missing_credentials_returns_401(db_session):
    with pytest.raises(HTTPException) as exc_info:
        authentication.get_current_user(
            credentials=None,
            db=db_session,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"


def test_invalid_token_returns_401(db_session, monkeypatch):
    def mock_verify_access_token(token):
        raise InvalidTokenError("Invalid token")

    monkeypatch.setattr(
        authentication,
        "verify_access_token",
        mock_verify_access_token,
    )

    with pytest.raises(HTTPException) as exc_info:
        authentication.get_current_user(
            credentials=create_credentials(),
            db=db_session,
        )

    assert exc_info.value.status_code == 401


def test_incomplete_oidc_configuration_returns_503(
    db_session,
    monkeypatch,
):
    def mock_verify_access_token(token):
        raise RuntimeError("OIDC configuration is incomplete")

    monkeypatch.setattr(
        authentication,
        "verify_access_token",
        mock_verify_access_token,
    )

    with pytest.raises(HTTPException) as exc_info:
        authentication.get_current_user(
            credentials=create_credentials(),
            db=db_session,
        )

    assert exc_info.value.status_code == 503


def test_jwks_connection_failure_returns_503(db_session, monkeypatch):
    def mock_verify_access_token(token):
        raise PyJWKClientConnectionError("JWKS unavailable")

    monkeypatch.setattr(
        authentication,
        "verify_access_token",
        mock_verify_access_token,
    )

    with pytest.raises(HTTPException) as exc_info:
        authentication.get_current_user(
            credentials=create_credentials(),
            db=db_session,
        )

    assert exc_info.value.status_code == 503


def test_invalid_claims_return_401(db_session, monkeypatch):
    monkeypatch.setattr(
        authentication,
        "verify_access_token",
        lambda token: {
            "iss": "https://identity.example.com",
            "sub": "",
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        authentication.get_current_user(
            credentials=create_credentials(),
            db=db_session,
        )

    assert exc_info.value.status_code == 401


def test_unknown_identity_returns_401(db_session, monkeypatch):
    monkeypatch.setattr(
        authentication,
        "verify_access_token",
        lambda token: {
            "iss": "https://identity.example.com",
            "sub": "unknown-subject",
        },
    )

    monkeypatch.setattr(
        authentication,
        "resolve_authenticated_user",
        lambda db, *, issuer, subject: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        authentication.get_current_user(
            credentials=create_credentials(),
            db=db_session,
        )

    assert exc_info.value.status_code == 401


def test_valid_token_returns_authenticated_user(db_session, monkeypatch):
    user = User(
        email="authenticated@example.com",
        full_name="Authenticated User",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    monkeypatch.setattr(
        authentication,
        "verify_access_token",
        lambda token: {
            "iss": "https://identity.example.com",
            "sub": "subject-123",
        },
    )

    def mock_resolve_user(db, *, issuer, subject):
        assert issuer == "https://identity.example.com"
        assert subject == "subject-123"
        return user

    monkeypatch.setattr(
        authentication,
        "resolve_authenticated_user",
        mock_resolve_user,
    )

    result = authentication.get_current_user(
        credentials=create_credentials(),
        db=db_session,
    )

    assert result.id == user.id


def test_identity_is_in_context_before_the_user_is_resolved(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(
        authentication,
        "verify_access_token",
        lambda token: {
            "iss": "https://identity.example.com",
            "sub": "subject-123",
        },
    )

    seen = {}

    def mock_resolve_user(db, *, issuer, subject):
        seen.update(db.info)
        return None

    monkeypatch.setattr(
        authentication,
        "resolve_authenticated_user",
        mock_resolve_user,
    )

    with pytest.raises(HTTPException):
        authentication.get_current_user(
            credentials=create_credentials(),
            db=db_session,
        )

    assert seen["auth_issuer"] == "https://identity.example.com"
    assert seen["auth_subject"] == "subject-123"
    assert seen["user_id"] is None
