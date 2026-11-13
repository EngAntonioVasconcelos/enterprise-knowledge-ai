import uuid

import pytest
from fastapi import HTTPException

from app.api.dependencies.authorization import (
    get_current_membership,
    require_roles,
)
from app.db.context import set_identity_context
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.user import User


def create_organization(db_session, name: str) -> Organization:
    organization = Organization(
        name=name,
        slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(organization)
    db_session.flush()
    return organization


def create_user(db_session, email: str) -> User:
    user = User(
        email=email,
        full_name="Test User",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def create_membership(
    db_session,
    organization: Organization,
    user: User,
    role: str = "member",
    is_active: bool = True,
) -> OrganizationMembership:
    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=user.id,
        role=role,
        has_held_privileged_role=role in {"owner", "admin"},
        is_active=is_active,
    )
    db_session.add(membership)
    db_session.flush()
    return membership


def establish_test_identity(db_session, user: User) -> None:
    set_identity_context(
        db_session,
        issuer="https://identity.example.com/",
        subject=f"test-subject-{user.id}",
        user_id=user.id,
    )


def test_active_member_can_get_current_membership(db_session):
    organization = create_organization(db_session, "Organization One")
    user = create_user(db_session, "member@example.com")
    membership = create_membership(db_session, organization, user)
    establish_test_identity(db_session, user)

    result = get_current_membership(
        organization_id=organization.id,
        current_user=user,
        db=db_session,
    )

    assert result.id == membership.id
    assert result.user_id == user.id
    assert result.organization_id == organization.id
    assert db_session.info["organization_id"] == str(organization.id)


def test_user_without_membership_receives_404(db_session):
    organization = create_organization(db_session, "Organization Two")
    user = create_user(db_session, "outsider@example.com")
    establish_test_identity(db_session, user)

    with pytest.raises(HTTPException) as exc_info:
        get_current_membership(
            organization_id=organization.id,
            current_user=user,
            db=db_session,
        )

    assert exc_info.value.status_code == 404
    assert db_session.info.get("organization_id") is None


def test_user_from_another_organization_receives_404(db_session):
    first_organization = create_organization(
        db_session,
        "Organization Three",
    )
    second_organization = create_organization(
        db_session,
        "Organization Four",
    )
    user = create_user(db_session, "other-org@example.com")

    create_membership(
        db_session,
        first_organization,
        user,
    )
    establish_test_identity(db_session, user)

    with pytest.raises(HTTPException) as exc_info:
        get_current_membership(
            organization_id=second_organization.id,
            current_user=user,
            db=db_session,
        )

    assert exc_info.value.status_code == 404
    assert db_session.info.get("organization_id") is None


def test_allowed_role_can_access_protected_operation(db_session):
    organization = create_organization(db_session, "Organization Five")
    user = create_user(db_session, "admin@example.com")

    membership = create_membership(
        db_session,
        organization,
        user,
        role="admin",
    )

    role_dependency = require_roles(["owner", "admin"])

    result = role_dependency(membership=membership)

    assert result.id == membership.id
    assert result.role == "admin"


def test_insufficient_role_receives_403(db_session):
    organization = create_organization(db_session, "Organization Six")
    user = create_user(db_session, "viewer@example.com")

    membership = create_membership(
        db_session,
        organization,
        user,
        role="viewer",
    )

    role_dependency = require_roles(["owner", "admin"])

    with pytest.raises(HTTPException) as exc_info:
        role_dependency(membership=membership)

    assert exc_info.value.status_code == 403


def test_invalid_allowed_role_is_rejected():
    with pytest.raises(ValueError):
        require_roles(["superadmin"])


def test_inactive_membership_receives_404(db_session):
    organization = create_organization(
        db_session,
        "Organization Seven",
    )
    user = create_user(
        db_session,
        "inactive-membership@example.com",
    )

    create_membership(
        db_session,
        organization,
        user,
        role="member",
        is_active=False,
    )
    establish_test_identity(db_session, user)

    with pytest.raises(HTTPException) as exc_info:
        get_current_membership(
            organization_id=organization.id,
            current_user=user,
            db=db_session,
        )

    assert exc_info.value.status_code == 404
    assert db_session.info.get("organization_id") is None
