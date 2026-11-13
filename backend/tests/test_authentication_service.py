
from datetime import datetime, timezone

from app.models.authentication_identity import AuthenticationIdentity
from app.models.user import User
from app.services.authentication_service import resolve_authenticated_user


def create_user(db_session, email: str, full_name: str = "Test User") -> User:
    user = User(
        email=email,
        full_name=full_name,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def create_identity(
    db_session,
    user: User,
    issuer: str,
    subject: str,
    is_active: bool = True,
) -> AuthenticationIdentity:
    identity = AuthenticationIdentity(
        user_id=user.id,
        issuer=issuer,
        subject=subject,
        is_active=is_active,
    )
    db_session.add(identity)
    db_session.flush()
    return identity



def test_resolves_active_identity_to_user(db_session):
    user = create_user(db_session, "active@example.com")
    identity = create_identity(
        db_session,
        user,
        "https://identity.example.com",
        "subject-123",
    )

    result = resolve_authenticated_user(
        db_session,
        issuer="https://identity.example.com",
        subject="subject-123",
    )

    assert result is not None
    assert result.id == user.id
    assert identity.last_authenticated_at is None



def test_returns_none_for_unknown_identity(db_session):
    result = resolve_authenticated_user(
        db_session,
        issuer="https://identity.example.com",
        subject="unknown-subject",
    )

    assert result is None


def test_returns_none_for_inactive_identity(db_session):
    user = create_user(db_session, "inactive-identity@example.com")
    identity = create_identity(
        db_session,
        user,
        "https://identity.example.com",
        "inactive-subject",
        is_active=False,
    )

    result = resolve_authenticated_user(
        db_session,
        issuer="https://identity.example.com",
        subject="inactive-subject",
    )

    assert result is None
    assert identity.last_authenticated_at is None


def test_returns_none_for_inactive_user(db_session):
    user = create_user(db_session, "inactive-user@example.com")
    user.is_active = False

    identity = create_identity(
        db_session,
        user,
        "https://identity.example.com",
        "inactive-user-subject",
    )

    result = resolve_authenticated_user(
        db_session,
        issuer="https://identity.example.com",
        subject="inactive-user-subject",
    )

    assert result is None
    assert identity.last_authenticated_at is None


def test_same_subject_from_different_issuers_resolves_correct_user(db_session):
    first_user = create_user(db_session, "first@example.com")
    second_user = create_user(db_session, "second@example.com")

    create_identity(
        db_session,
        first_user,
        "https://provider-one.example.com",
        "shared-subject",
    )
    create_identity(
        db_session,
        second_user,
        "https://provider-two.example.com",
        "shared-subject",
    )

    result = resolve_authenticated_user(
        db_session,
        issuer="https://provider-two.example.com",
        subject="shared-subject",
    )

    assert result is not None
    assert result.id == second_user.id
