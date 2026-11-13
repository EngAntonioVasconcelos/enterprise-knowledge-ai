
import pytest
from sqlalchemy.exc import IntegrityError

from app.models import AuthenticationIdentity, User


def create_test_user(db_session):
    user = User(
        email="identity@example.com",
        full_name="Identity Test User",
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_authentication_identity_belongs_to_user(db_session):
    user = create_test_user(db_session)

    identity = AuthenticationIdentity(
        user_id=user.id,
        issuer="https://identity.example.com/",
        subject="external-user-123",
    )

    db_session.add(identity)
    db_session.flush()

    assert identity.user_id == user.id
    assert identity.user.id == user.id
    assert identity in user.authentication_identities


def test_user_can_have_multiple_authentication_identities(db_session):
    user = create_test_user(db_session)

    identities = [
        AuthenticationIdentity(
            issuer="https://login.microsoftonline.com/tenant/",
            subject="microsoft-user-123",
        ),
        AuthenticationIdentity(
            issuer="https://accounts.google.com/",
            subject="google-user-456",
        ),
    ]

    user.authentication_identities.extend(identities)
    db_session.flush()

    assert len(user.authentication_identities) == 2
    assert all(identity.user_id == user.id for identity in identities)


def test_authentication_identity_issuer_subject_must_be_unique(db_session):
    user = create_test_user(db_session)

    first_identity = AuthenticationIdentity(
        user_id=user.id,
        issuer="https://identity.example.com/",
        subject="external-user-123",
    )

    second_identity = AuthenticationIdentity(
        user_id=user.id,
        issuer="https://identity.example.com/",
        subject="external-user-123",
    )

    db_session.add(first_identity)
    db_session.flush()

    db_session.add(second_identity)

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()



def test_same_subject_can_exist_for_different_issuers(db_session):
    user = create_test_user(db_session)

    identities = [
        AuthenticationIdentity(
            user_id=user.id,
            issuer="https://provider-a.example.com/",
            subject="user-123",
        ),
        AuthenticationIdentity(
            user_id=user.id,
            issuer="https://provider-b.example.com/",
            subject="user-123",
        ),
    ]

    db_session.add_all(identities)
    db_session.flush()

    assert len(user.authentication_identities) == 2
    assert identities[0].subject == identities[1].subject
    assert identities[0].issuer != identities[1].issuer
    assert all(identity.user_id == user.id for identity in identities)
