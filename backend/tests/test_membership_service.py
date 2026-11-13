
import uuid

import pytest

from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.user import User

from app.services.membership_service import (
    MembershipPermissionError,
    _get_authorized_actor_membership,
    create_initial_owner_membership,
    create_membership,
    update_membership_role,
    deactivate_membership,
)


def create_test_organization(db_session, suffix="acme"):
    organization = Organization(
        name="Acme Corporation",
        slug=f"acme-{suffix}-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(organization)
    db_session.flush()
    return organization


def create_test_user(db_session, email="employee@example.com"):
    user = User(
        email=email,
        full_name="John Smith",
    )
    db_session.add(user)
    db_session.flush()
    return user


def create_test_membership(
    db_session,
    organization,
    user,
    role="member",
    is_active=True,
):
    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=user.id,
        role=role,
        has_held_privileged_role=role in {"owner", "admin"},
        has_held_owner_role=role == "owner",
        is_active=is_active,
    )
    db_session.add(membership)
    db_session.flush()
    return membership

def create_test_owner(db_session, organization):
    owner = create_test_user(
        db_session,
        email=f"owner-{uuid.uuid4().hex}@example.com",
    )

    membership = create_test_membership(
        db_session,
        organization,
        owner,
        role="owner",
    )

    return owner, membership

def create_test_owner_context(db_session):
    organization = create_test_organization(db_session)
    owner, _ = create_test_owner(db_session, organization)

    return organization, owner



def test_create_initial_owner_rejects_existing_membership(db_session):
    organization = create_test_organization(db_session)

    existing_user = create_test_user(
        db_session,
        email="existing-member@example.com",
    )

    create_test_membership(
        db_session,
        organization,
        existing_user,
        role="member",
    )

    new_owner = create_test_user(
        db_session,
        email="new-owner@example.com",
    )

    with pytest.raises(
        ValueError,
        match="without existing memberships",
    ):
        create_initial_owner_membership(
            db_session,
            organization_id=organization.id,
            user_id=new_owner.id,
        )


def test_create_test_owner(db_session):
    organization = create_test_organization(db_session)

    owner, membership = create_test_owner(
        db_session,
        organization,
    )

    assert owner.id == membership.user_id
    assert membership.organization_id == organization.id
    assert membership.role == "owner"
    assert membership.is_active is True

def test_authorized_actor_membership_accepts_owner(db_session):
    from app.services.membership_service import (
        _get_authorized_actor_membership,
    )

    organization = create_test_organization(db_session)
    owner, membership = create_test_owner(db_session, organization)

    result = _get_authorized_actor_membership(
        db_session,
        organization_id=organization.id,
        actor_user_id=owner.id,
        allowed_roles={"owner"},
    )

    assert result.id == membership.id
    assert result.role == "owner"


def test_authorized_actor_membership_rejects_admin_when_owner_required(
    db_session,
):
    from app.services.membership_service import (
        _get_authorized_actor_membership,
    )

    organization = create_test_organization(db_session)
    admin = create_test_user(
        db_session,
        email="admin@example.com",
    )
    create_test_membership(
        db_session,
        organization,
        admin,
        role="admin",
    )

    with pytest.raises(
        MembershipPermissionError,
        match="Insufficient organization permissions",
    ):
        _get_authorized_actor_membership(
            db_session,
            organization_id=organization.id,
            actor_user_id=admin.id,
            allowed_roles={"owner"},
        )


def test_authorized_actor_membership_rejects_non_member(db_session):
    from app.services.membership_service import (
        _get_authorized_actor_membership,
    )

    organization = create_test_organization(db_session)
    user = create_test_user(db_session)

    with pytest.raises(
        ValueError,
        match="not an active member",
    ):
        _get_authorized_actor_membership(
            db_session,
            organization_id=organization.id,
            actor_user_id=user.id,
            allowed_roles={"owner", "admin"},
        )


def test_create_membership(db_session):
    from app.services.membership_service import create_membership

    organization, owner = create_test_owner_context(db_session)
    user = create_test_user(db_session)

    membership = create_membership(
        db_session,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=user.id,
    )

    assert membership.id is not None
    assert membership.organization_id == organization.id
    assert membership.user_id == user.id
    assert membership.role == "member"
    assert membership.is_active is True


def test_create_membership_with_specific_role(db_session):
    from app.services.membership_service import create_membership

    organization, owner = create_test_owner_context(db_session)
    user = create_test_user(db_session)

    membership = create_membership(
        db_session,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=user.id,
        role="admin",
    )

    assert membership.role == "admin"
    assert membership.is_active is True


def test_create_membership_rejects_duplicate_active_membership(
    db_session,
):
    from app.services.membership_service import create_membership

    organization, owner = create_test_owner_context(db_session)
    user = create_test_user(db_session)

    create_test_membership(db_session, organization, user)

    with pytest.raises(ValueError, match="already exists"):
        create_membership(
            db_session,
            organization_id=organization.id,
            actor_user_id=owner.id,
            user_id=user.id,
        )


def test_create_membership_reactivates_inactive_membership(
    db_session,
):
    from app.services.membership_service import create_membership

    organization, owner = create_test_owner_context(db_session)
    user = create_test_user(db_session)

    previous_membership = create_test_membership(
        db_session,
        organization,
        user,
        role="viewer",
        is_active=False,
    )

    membership = create_membership(
        db_session,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=user.id,
        role="member",
    )

    assert membership.id == previous_membership.id
    assert membership.is_active is True
    assert membership.role == "member"

def test_get_membership(db_session):
    from app.services.membership_service import get_membership

    organization = create_test_organization(db_session)
    user = create_test_user(db_session)

    membership = create_test_membership(
        db_session,
        organization,
        user,
    )

    result = get_membership(
        db_session,
        organization_id=organization.id,
        user_id=user.id,
    )

    assert result is not None
    assert result.id == membership.id


def test_list_organization_memberships(db_session):
    from app.services.membership_service import (
        list_organization_memberships,
    )

    organization = create_test_organization(db_session)
    first_user = create_test_user(
        db_session,
        "first@example.com",
    )
    second_user = create_test_user(
        db_session,
        "second@example.com",
    )

    create_test_membership(
        db_session,
        organization,
        first_user,
        role="member",
    )
    create_test_membership(
        db_session,
        organization,
        second_user,
        role="viewer",
        is_active=False,
    )

    memberships = list_organization_memberships(
        db_session,
        organization_id=organization.id,
    )

    assert len(memberships) == 1
    assert memberships[0].user_id == first_user.id



def test_update_membership_role(db_session):
    from app.services.membership_service import update_membership_role

    organization, owner = create_test_owner_context(db_session)
    target_user = create_test_user(
        db_session,
        email="target@example.com",
    )

    membership = create_test_membership(
        db_session,
        organization,
        target_user,
        role="member",
    )

    updated = update_membership_role(
        db_session,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=target_user.id,
        role="admin",
    )

    assert updated.id == membership.id
    assert updated.role == "admin"
    assert updated.is_active is True



def test_deactivate_membership_does_not_deactivate_global_user(
    db_session,
):
    from app.services.membership_service import deactivate_membership

    organization, owner = create_test_owner_context(db_session)
    user = create_test_user(db_session)

    membership = create_test_membership(
        db_session,
        organization,
        user,
    )

    deactivate_membership(
        db_session,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=user.id,
    )

    assert membership.is_active is False
    assert user.is_active is True




def test_cannot_deactivate_last_active_owner(db_session):
    from app.services.membership_service import deactivate_membership

    organization = create_test_organization(db_session)
    owner = create_test_user(db_session)

    membership = create_test_membership(
        db_session,
        organization,
        owner,
        role="owner",
    )

    with pytest.raises(ValueError, match="last active owner"):
        deactivate_membership(
            db_session,
            organization_id=organization.id,
            actor_user_id=owner.id,
            user_id=owner.id,
        )

    assert membership.is_active is True



def test_cannot_demote_last_active_owner(db_session):
    from app.services.membership_service import update_membership_role

    organization = create_test_organization(db_session)
    owner = create_test_user(db_session)

    membership = create_test_membership(
        db_session,
        organization,
        owner,
        role="owner",
    )

    with pytest.raises(ValueError, match="last active owner"):
        update_membership_role(
    db_session,
    organization_id=organization.id,
    actor_user_id=owner.id,
    user_id=owner.id,
    role="admin",
)

    assert membership.role == "owner"


def test_create_membership_rejects_inactive_user(db_session):
    from app.services.membership_service import create_membership

    organization, owner = create_test_owner_context(db_session)
    user = create_test_user(db_session)
    user.is_active = False
    db_session.flush()

    with pytest.raises(ValueError, match="inactive user"):
        create_membership(
            db_session,
            organization_id=organization.id,
            actor_user_id=owner.id,
            user_id=user.id,
        )


def test_create_membership_rejects_missing_organization(db_session):
    from app.services.membership_service import create_membership

    user = create_test_user(db_session)

    with pytest.raises(ValueError, match="Organization not found"):
        create_membership(
            db_session,
            organization_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
            user_id=user.id,
        )


def test_create_membership_rejects_invalid_role(db_session):
    from app.services.membership_service import create_membership

    organization, owner = create_test_owner_context(db_session)
    user = create_test_user(db_session)

    with pytest.raises(ValueError, match="Invalid membership role"):
        create_membership(
            db_session,
            organization_id=organization.id,
            actor_user_id=owner.id,
            user_id=user.id,
            role="super_admin",
        )

def test_can_deactivate_owner_when_another_active_owner_exists(db_session):
    from app.services.membership_service import deactivate_membership

    organization = create_test_organization(db_session)
    first_owner = create_test_user(db_session, "first-owner@example.com")
    second_owner = create_test_user(db_session, "second-owner@example.com")

    membership = create_test_membership(
        db_session, organization, first_owner, role="owner"
    )
    create_test_membership(
        db_session, organization, second_owner, role="owner"
    )

    deactivate_membership(
    db_session,
    organization_id=organization.id,
    actor_user_id=second_owner.id,
    user_id=first_owner.id,
)

    assert membership.is_active is False


def test_can_demote_owner_when_another_active_owner_exists(db_session):
    from app.services.membership_service import update_membership_role

    organization = create_test_organization(db_session)
    first_owner = create_test_user(db_session, "first-owner@example.com")
    second_owner = create_test_user(db_session, "second-owner@example.com")

    membership = create_test_membership(
        db_session, organization, first_owner, role="owner"
    )
    create_test_membership(
        db_session, organization, second_owner, role="owner"
    )
    update_membership_role(
    db_session,
    organization_id=organization.id,
    actor_user_id=second_owner.id,
    user_id=first_owner.id,
    role="admin",
)

    assert membership.role == "admin"



def test_cannot_update_inactive_membership(db_session):
    from app.services.membership_service import update_membership_role

    organization, owner = create_test_owner_context(db_session)
    user = create_test_user(db_session)

    membership = create_test_membership(
        db_session,
        organization,
        user,
        role="viewer",
        is_active=False,
    )

    with pytest.raises(ValueError, match="inactive membership"):
        update_membership_role(
            db_session,
            organization_id=organization.id,
            actor_user_id=owner.id,
            user_id=user.id,
            role="admin",
        )

    assert membership.role == "viewer"
    assert membership.is_active is False



def test_admin_cannot_reactivate_previous_owner_as_admin(db_session):
    from app.services.membership_service import create_membership

    organization, owner = create_test_owner_context(db_session)
    admin = create_test_user(db_session, "admin-reactivation@example.com")
    create_test_membership(db_session, organization, admin, role="admin")

    previous_owner = create_test_user(
        db_session,
        "previous-owner-admin@example.com",
    )
    create_test_membership(
        db_session,
        organization,
        previous_owner,
        role="owner",
        is_active=False,
    )

    with pytest.raises(MembershipPermissionError):
        create_membership(
            db_session,
            organization_id=organization.id,
            actor_user_id=admin.id,
            user_id=previous_owner.id,
            role="admin",
        )


def test_admin_cannot_reactivate_previous_admin_as_member(db_session):
    from app.services.membership_service import create_membership

    organization, owner = create_test_owner_context(db_session)
    admin = create_test_user(db_session, "admin-demotion@example.com")
    create_test_membership(db_session, organization, admin, role="admin")

    previous_admin = create_test_user(
        db_session,
        "previous-admin@example.com",
    )
    create_test_membership(
        db_session,
        organization,
        previous_admin,
        role="admin",
        is_active=False,
    )

    with pytest.raises(MembershipPermissionError):
        create_membership(
            db_session,
            organization_id=organization.id,
            actor_user_id=admin.id,
            user_id=previous_admin.id,
            role="member",
        )


def test_admin_cannot_reactivate_previous_owner_as_member(db_session):
    from app.services.membership_service import create_membership

    organization, owner = create_test_owner_context(db_session)
    admin = create_test_user(
        db_session,
        "admin-member-reactivation@example.com",
    )
    create_test_membership(
        db_session,
        organization,
        admin,
        role="admin",
    )

    previous_owner = create_test_user(
        db_session,
        "previous-owner-member@example.com",
    )
    previous_membership = create_test_membership(
        db_session,
        organization,
        previous_owner,
        role="owner",
        is_active=False,
    )

    with pytest.raises(MembershipPermissionError):
        create_membership(
            db_session,
            organization_id=organization.id,
            actor_user_id=admin.id,
            user_id=previous_owner.id,
            role="member",
        )

    assert previous_membership.is_active is False
    assert previous_membership.role == "owner"



def test_admin_cannot_deactivate_another_admin(db_session):
    from app.services.membership_service import deactivate_membership

    organization, owner = create_test_owner_context(db_session)

    admin = create_test_user(db_session, "active-admin@example.com")
    create_test_membership(db_session, organization, admin, role="admin")

    target_admin = create_test_user(
        db_session,
        "target-admin@example.com",
    )
    target_membership = create_test_membership(
        db_session,
        organization,
        target_admin,
        role="admin",
    )

    with pytest.raises(MembershipPermissionError):
        deactivate_membership(
            db_session,
            organization_id=organization.id,
            actor_user_id=admin.id,
            user_id=target_admin.id,
        )

    assert target_membership.is_active is True


def test_admin_cannot_deactivate_an_owner(db_session):
    from app.services.membership_service import deactivate_membership

    organization, owner = create_test_owner_context(db_session)

    admin = create_test_user(db_session, "owner-protection-admin@example.com")
    create_test_membership(db_session, organization, admin, role="admin")

    with pytest.raises(MembershipPermissionError):
        deactivate_membership(
            db_session,
            organization_id=organization.id,
            actor_user_id=admin.id,
            user_id=owner.id,
        )


def test_admin_can_deactivate_a_member(db_session):
    from app.services.membership_service import deactivate_membership

    organization, owner = create_test_owner_context(db_session)

    admin = create_test_user(db_session, "member-deactivation-admin@example.com")
    create_test_membership(db_session, organization, admin, role="admin")

    member = create_test_user(db_session, "member-to-deactivate@example.com")
    membership = create_test_membership(
        db_session,
        organization,
        member,
        role="member",
    )

    result = deactivate_membership(
        db_session,
        organization_id=organization.id,
        actor_user_id=admin.id,
        user_id=member.id,
    )

    assert result.id == membership.id
    assert result.is_active is False
    assert member.is_active is True


def test_owner_can_deactivate_an_admin(db_session):
    from app.services.membership_service import deactivate_membership

    organization, owner = create_test_owner_context(db_session)

    admin = create_test_user(db_session, "admin-to-deactivate@example.com")
    membership = create_test_membership(
        db_session,
        organization,
        admin,
        role="admin",
    )

    result = deactivate_membership(
        db_session,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=admin.id,
    )

    assert result.id == membership.id
    assert result.is_active is False


def test_reactivating_previous_owner_as_member_does_not_restore_owner_role(
    db_session,
):
    from app.services.membership_service import create_membership

    organization, active_owner = create_test_owner_context(db_session)
    previous_owner = create_test_user(
        db_session,
        email="previous-owner@example.com",
    )

    previous_membership = create_test_membership(
        db_session,
        organization,
        previous_owner,
        role="owner",
        is_active=False,
    )

    membership = create_membership(
        db_session,
        organization_id=organization.id,
        actor_user_id=active_owner.id,
        user_id=previous_owner.id,
        role="member",
    )

    assert membership.id == previous_membership.id
    assert membership.is_active is True
    assert membership.role == "member"


def test_can_reactivate_previous_owner_when_another_active_owner_exists(
    db_session,
):
    from app.services.membership_service import create_membership

    organization, active_owner = create_test_owner_context(db_session)
    previous_owner = create_test_user(
        db_session,
        email="previous-owner@example.com",
    )

    previous_membership = create_test_membership(
        db_session,
        organization,
        previous_owner,
        role="owner",
        is_active=False,
    )

    membership = create_membership(
        db_session,
        organization_id=organization.id,
        actor_user_id=active_owner.id,
        user_id=previous_owner.id,
        role="owner",
    )

    assert membership.id == previous_membership.id
    assert membership.is_active is True
    assert membership.role == "owner"

@pytest.mark.parametrize("previous_role", ["owner", "admin"])
def test_admin_cannot_deactivate_inactive_historically_privileged_membership(
    db_session,
    previous_role,
):
    from app.services.membership_service import deactivate_membership

    organization, _ = create_test_owner_context(db_session)

    admin = create_test_user(
        db_session,
        email=f"admin-{uuid.uuid4().hex}@example.com",
    )
    create_test_membership(
        db_session,
        organization,
        admin,
        role="admin",
    )

    previous_privileged_user = create_test_user(
        db_session,
        email=f"previous-{uuid.uuid4().hex}@example.com",
    )
    previous_membership = create_test_membership(
        db_session,
        organization,
        previous_privileged_user,
        role=previous_role,
        is_active=False,
    )

    with pytest.raises(MembershipPermissionError):
        deactivate_membership(
            db_session,
            organization_id=organization.id,
            actor_user_id=admin.id,
            user_id=previous_privileged_user.id,
        )

    assert previous_membership.is_active is False
    assert previous_membership.has_held_privileged_role is True

def test_database_rejects_admin_without_privileged_history(db_session):
    from sqlalchemy.exc import IntegrityError

    organization = create_test_organization(db_session)
    user = create_test_user(
        db_session,
        email="invalid-admin-history@example.com",
    )

    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=user.id,
        role="admin",
        has_held_privileged_role=False,
        is_active=True,
    )

    db_session.add(membership)

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_database_accepts_member_with_privileged_history(db_session):
    organization = create_test_organization(db_session)
    user = create_test_user(
        db_session,
        email="demoted-admin-history@example.com",
    )

    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=user.id,
        role="member",
        has_held_privileged_role=True,
        is_active=True,
    )

    db_session.add(membership)
    db_session.flush()

    assert membership.role == "member"
    assert membership.has_held_privileged_role is True



def test_owner_cannot_create_membership_in_another_organization(
    db_session,
):
    organization_a, owner_a = create_test_owner_context(db_session)
    organization_b = create_test_organization(db_session, suffix="other")
    target_user = create_test_user(
        db_session,
        email=f"target-{uuid.uuid4().hex}@example.com",
    )

    with pytest.raises(
        ValueError,
        match="Actor is not an active member",
    ):
        create_membership(
            db_session,
            organization_id=organization_b.id,
            actor_user_id=owner_a.id,
            user_id=target_user.id,
            role="member",
        )

    assert db_session.query(OrganizationMembership).filter_by(
        organization_id=organization_b.id,
        user_id=target_user.id,
    ).count() == 0


def test_owner_cannot_update_membership_in_another_organization(
    db_session,
):
    organization_a, owner_a = create_test_owner_context(db_session)
    organization_b = create_test_organization(db_session, suffix="other")

    target_user = create_test_user(
        db_session,
        email=f"target-{uuid.uuid4().hex}@example.com",
    )
    target_membership = create_test_membership(
        db_session,
        organization_b,
        target_user,
        role="member",
    )

    with pytest.raises(
        ValueError,
        match="Actor is not an active member",
    ):
        update_membership_role(
            db_session,
            organization_id=organization_b.id,
            actor_user_id=owner_a.id,
            user_id=target_user.id,
            role="admin",
        )

    db_session.refresh(target_membership)
    assert target_membership.role == "member"


def test_owner_cannot_deactivate_membership_in_another_organization(
    db_session,
):
    organization_a, owner_a = create_test_owner_context(db_session)
    organization_b = create_test_organization(db_session, suffix="other")

    target_user = create_test_user(
        db_session,
        email=f"target-{uuid.uuid4().hex}@example.com",
    )
    target_membership = create_test_membership(
        db_session,
        organization_b,
        target_user,
        role="member",
    )

    with pytest.raises(
        ValueError,
        match="Actor is not an active member",
    ):
        deactivate_membership(
            db_session,
            organization_id=organization_b.id,
            actor_user_id=owner_a.id,
            user_id=target_user.id,
        )

    db_session.refresh(target_membership)
    assert target_membership.is_active is True

