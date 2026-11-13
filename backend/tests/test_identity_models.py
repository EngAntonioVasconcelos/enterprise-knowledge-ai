
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Organization, User
from app.models.membership import OrganizationMembership



def create_organization(db_session, name):
    organization = Organization(
        name=name,
        slug=f"{name.lower()}-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(organization)
    db_session.flush()
    return organization


def create_user(db_session, email="employee@example.com"):
    user = User(
        email=email,
        full_name="John Smith",
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_user_is_global_identity(db_session):
    user = create_user(db_session)

    assert user.id is not None
    assert user.email == "employee@example.com"
    assert not hasattr(user, "organization_id")
    assert not hasattr(user, "role")


def test_user_can_belong_to_multiple_organizations(db_session):
    first_organization = create_organization(
        db_session,
        "Alpha",
    )
    second_organization = create_organization(
        db_session,
        "Beta",
    )
    user = create_user(db_session)

    first_membership = OrganizationMembership(
        organization=first_organization,
        user=user,
        role="admin",
        has_held_privileged_role=True,
    )

    second_membership = OrganizationMembership(
        organization=second_organization,
        user=user,
        role="member",
    )

    db_session.add_all([
        first_membership,
        second_membership,
    ])
    db_session.flush()

    assert len(user.memberships) == 2
    assert first_membership.role == "admin"
    assert second_membership.role == "member"
def test_membership_deactivation_does_not_deactivate_user(db_session):
    first_organization = create_organization(db_session, "Alpha")
    second_organization = create_organization(db_session, "Beta")
    user = create_user(db_session)

    first_membership = OrganizationMembership(
        organization=first_organization,
        user=user,
        role="member",
    )

    second_membership = OrganizationMembership(
        organization=second_organization,
        user=user,
        role="admin",
        has_held_privileged_role=True,
    )

    db_session.add_all([
        first_membership,
        second_membership,
    ])
    db_session.flush()

    first_membership.is_active = False
    db_session.flush()

    assert user.is_active is True
    assert first_membership.is_active is False
    assert second_membership.is_active is True


def test_deleting_organization_does_not_delete_global_user(db_session):
    organization = create_organization(db_session, "Alpha")
    user = create_user(db_session)

    membership = OrganizationMembership(
        organization=organization,
        user=user,
        role="member",
    )

    db_session.add(membership)
    db_session.commit()

    user_id = user.id
    organization_id = organization.id

    db_session.delete(organization)
    db_session.commit()

    remaining_user = db_session.get(User, user_id)
    remaining_organization = db_session.get(
        Organization,
        organization_id,
    )

    assert remaining_user is not None
    assert remaining_organization is None

def test_membership_is_unique_per_organization_and_user(db_session):
    organization = create_organization(db_session, "Alpha")
    user = create_user(db_session)

    first_membership = OrganizationMembership(
        organization=organization,
        user=user,
        role="member",
    )

    db_session.add(first_membership)
    db_session.commit()

    duplicate_membership = OrganizationMembership(
        organization=organization,
        user=user,
        role="admin",
        has_held_privileged_role=True,
    )

    db_session.add(duplicate_membership)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_membership_rejects_invalid_role(db_session):
    organization = create_organization(db_session, "Alpha")
    user = create_user(db_session)

    invalid_membership = OrganizationMembership(
        organization=organization,
        user=user,
        role="super_admin",
    )

    db_session.add(invalid_membership)

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_user_email_is_normalized_by_orm(db_session):
    user = create_user(
        db_session,
        email="USER@EXAMPLE.COM",
    )

    assert user.email == "user@example.com"


def test_database_rejects_non_normalized_email(db_session):
    user = User(
        email="USER@EXAMPLE.COM",
        full_name="John Smith",
    )

    # Bypass the ORM validator to simulate a direct database insert.
    user.__dict__["email"] = "USER@EXAMPLE.COM"

    db_session.add(user)

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()