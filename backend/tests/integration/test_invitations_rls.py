import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

from app.db.context import set_organization_context
from app.models import OrganizationInvitation, OrganizationMembership
from app.services import invitation_service
from app.services.invitation_service import (
    AlreadyMemberError,
    InvitationEmailMismatchError,
    InvitationNotFoundError,
    accept_invitation,
    create_invitation,
    revoke_invitation,
)
from app.services.membership_service import create_membership
from tests.integration.test_postgres_rls import (
    _authenticate,
    _create_organization,
    _create_user,
)


pytestmark = pytest.mark.integration


def _setup(db):
    owner = _create_user(db, "invite-owner")
    guest = _create_user(db, "invite-guest")
    organization = _create_organization(db, owner)
    _authenticate(db, owner)
    set_organization_context(db, organization_id=organization.id)
    return owner, guest, organization


def _invite(db, owner, organization, email, role="member"):
    return create_invitation(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        email=email,
        role=role,
    )


def test_invitee_joins_with_the_invited_role(postgres_db_session):
    db = postgres_db_session
    owner, guest, organization = _setup(db)
    invitation, token = _invite(db, owner, organization, guest.email, "admin")

    _authenticate(db, guest)
    membership = accept_invitation(db, token=token)

    assert membership.organization_id == organization.id
    assert membership.user_id == guest.id
    assert (membership.role, membership.is_active) == ("admin", True)
    assert membership.has_held_privileged_role is True

    with pytest.raises(InvitationNotFoundError):
        with db.begin_nested():
            accept_invitation(db, token=token)

    _authenticate(db, owner)
    db.refresh(invitation)
    assert invitation.status == "accepted"
    assert invitation.accepted_by_user_id == guest.id


def test_invitation_for_another_email_is_refused(postgres_db_session):
    db = postgres_db_session
    owner, guest, organization = _setup(db)
    stranger = _create_user(db, "invite-stranger")
    _, token = _invite(db, owner, organization, guest.email)

    _authenticate(db, stranger)

    with pytest.raises(InvitationEmailMismatchError):
        with db.begin_nested():
            accept_invitation(db, token=token)


def test_revoked_expired_and_unknown_tokens_are_refused(
    postgres_db_session,
    monkeypatch,
):
    db = postgres_db_session
    owner, guest, organization = _setup(db)
    revoked, revoked_token = _invite(db, owner, organization, guest.email)
    revoke_invitation(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        invitation_id=revoked.id,
    )
    # The application cannot change an expiry date, so the invitation is
    # created already expired.
    monkeypatch.setattr(
        invitation_service, "INVITATION_LIFETIME", timedelta(hours=-1)
    )
    _, expired_token = _invite(db, owner, organization, guest.email)

    _authenticate(db, guest)

    for token in (revoked_token, expired_token, "unknown-" + "x" * 40):
        with pytest.raises(InvitationNotFoundError):
            with db.begin_nested():
                accept_invitation(db, token=token)


def test_active_member_cannot_accept_again(postgres_db_session):
    db = postgres_db_session
    owner, guest, organization = _setup(db)
    create_membership(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=guest.id,
        role="viewer",
    )
    _, token = _invite(db, owner, organization, guest.email)

    _authenticate(db, guest)

    with pytest.raises(AlreadyMemberError):
        with db.begin_nested():
            accept_invitation(db, token=token)


def test_invitations_are_visible_only_to_managers(postgres_db_session):
    db = postgres_db_session
    owner, guest, organization = _setup(db)
    _invite(db, owner, organization, guest.email)

    member = _create_user(db, "invite-member")
    create_membership(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=member.id,
        role="member",
    )
    outsider_owner = _create_user(db, "invite-outsider")
    _create_organization(db, outsider_owner)

    def visible():
        return db.scalars(
            select(OrganizationInvitation.id).where(
                OrganizationInvitation.organization_id == organization.id
            )
        ).all()

    _authenticate(db, owner)
    assert len(visible()) == 1

    for user in (guest, member, outsider_owner):
        _authenticate(db, user)
        assert visible() == []


def test_runtime_cannot_mark_an_invitation_accepted(postgres_db_session):
    db = postgres_db_session
    owner, guest, organization = _setup(db)
    invitation, _ = _invite(db, owner, organization, guest.email)

    with pytest.raises(DBAPIError, match="row-level security"):
        with db.begin_nested():
            db.execute(
                update(OrganizationInvitation)
                .where(OrganizationInvitation.id == invitation.id)
                .values(status="accepted")
            )


def test_non_members_cannot_join_without_an_invitation(postgres_db_session):
    db = postgres_db_session
    owner, guest, organization = _setup(db)

    _authenticate(db, guest)

    with pytest.raises(DBAPIError, match="row-level security"):
        with db.begin_nested():
            db.add(
                OrganizationMembership(
                    id=uuid.uuid4(),
                    organization_id=organization.id,
                    user_id=guest.id,
                    role="member",
                    is_active=True,
                )
            )
            db.flush()
