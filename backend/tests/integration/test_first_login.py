import uuid

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select, text

from app.api.dependencies import authentication
from app.db.context import set_authentication_context
from app.models import AuthenticationIdentity


pytestmark = pytest.mark.integration

ISSUER = "https://test-identity.example.com/"
CREDENTIALS = HTTPAuthorizationCredentials(scheme="Bearer", credentials="t")


def _login(db, monkeypatch, *, subject, email, verified=True):
    monkeypatch.setattr(
        authentication,
        "verify_access_token",
        lambda token: {
            "iss": ISSUER,
            "sub": subject,
            "email": email,
            "email_verified": verified,
            "name": "First Login",
        },
    )
    return authentication.get_current_user(credentials=CREDENTIALS, db=db)


def test_first_login_creates_account_and_identity(
    postgres_db_session,
    monkeypatch,
):
    db = postgres_db_session
    unique = uuid.uuid4().hex
    subject = f"first-{unique}"
    email = f"First.Login-{unique}@Example.com"

    user = _login(db, monkeypatch, subject=subject, email=email)

    assert user.email == email.lower()
    assert user.full_name == "First Login"

    identities = db.scalars(select(AuthenticationIdentity)).all()
    assert [(i.user_id, i.subject) for i in identities] == [
        (user.id, subject)
    ]

    again = _login(db, monkeypatch, subject=subject, email=email)
    assert again.id == user.id


def test_new_identity_with_the_same_verified_email_links_the_account(
    postgres_db_session,
    monkeypatch,
):
    db = postgres_db_session
    unique = uuid.uuid4().hex
    email = f"linked-{unique}@example.com"

    first = _login(db, monkeypatch, subject=f"google-{unique}", email=email)
    second = _login(db, monkeypatch, subject=f"password-{unique}", email=email)

    assert second.id == first.id


def test_unverified_email_creates_nothing(postgres_db_session, monkeypatch):
    db = postgres_db_session
    unique = uuid.uuid4().hex
    subject = f"unverified-{unique}"

    with pytest.raises(HTTPException) as exc_info:
        _login(
            db,
            monkeypatch,
            subject=subject,
            email=f"unverified-{unique}@example.com",
            verified=False,
        )

    assert exc_info.value.status_code == 403

    set_authentication_context(db, issuer=ISSUER, subject=subject)
    assert db.scalar(
        text("SELECT count(*) FROM authentication_identities")
    ) == 0
