import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models.invitation import OrganizationInvitation
from app.models.membership import OrganizationMembership
from app.services.membership_service import (
    _get_authorized_actor_membership,
    _lock_organization,
)


INVITATION_LIFETIME = timedelta(days=7)
PRIVILEGED_ROLES = {"owner", "admin"}


class InvitationError(Exception):
    """Base class for invitation errors the API reports to the caller."""


class InvitationAlreadyPendingError(InvitationError):
    pass


class InvitationNotFoundError(InvitationError):
    pass


class InvitationEmailMismatchError(InvitationError):
    pass


class AlreadyMemberError(InvitationError):
    pass


def hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    # SQLite, used by unit tests, returns naive datetimes.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def create_invitation(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    email: str,
    role: str,
) -> tuple[OrganizationInvitation, str]:
    """Create a pending invitation and return it with its one-time token.

    Inviting an owner or an admin requires an owner, the same rule as
    adding a membership directly.
    """
    _lock_organization(db, organization_id)

    _get_authorized_actor_membership(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        allowed_roles=(
            {"owner"} if role in PRIVILEGED_ROLES else {"owner", "admin"}
        ),
    )

    normalized_email = email.strip().lower()

    pending = db.scalar(
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.email == normalized_email,
            OrganizationInvitation.status == "pending",
        )
        .with_for_update()
    )

    if pending is not None:
        if _as_aware(pending.expires_at) > _now():
            raise InvitationAlreadyPendingError(
                "An invitation is already pending for this email"
            )

        pending.status = "expired"
        db.flush()

    token = secrets.token_urlsafe(32)

    invitation = OrganizationInvitation(
        organization_id=organization_id,
        email=normalized_email,
        role=role,
        token_hash=hash_invitation_token(token),
        status="pending",
        invited_by_user_id=actor_user_id,
        expires_at=_now() + INVITATION_LIFETIME,
    )

    db.add(invitation)
    db.flush()

    return invitation, token


def list_pending_invitations(
    db: Session,
    *,
    organization_id: uuid.UUID,
) -> list[OrganizationInvitation]:
    return list(
        db.scalars(
            select(OrganizationInvitation)
            .where(
                OrganizationInvitation.organization_id == organization_id,
                OrganizationInvitation.status == "pending",
            )
            .order_by(OrganizationInvitation.created_at.desc())
        )
    )


def revoke_invitation(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    invitation_id: uuid.UUID,
) -> OrganizationInvitation:
    invitation = db.scalar(
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.id == invitation_id,
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.status == "pending",
        )
        .with_for_update()
    )

    if invitation is None:
        raise InvitationNotFoundError("Invitation not found")

    _get_authorized_actor_membership(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        allowed_roles=(
            {"owner"}
            if invitation.role in PRIVILEGED_ROLES
            else {"owner", "admin"}
        ),
    )

    invitation.status = "revoked"
    db.flush()

    return invitation


_ACCEPT_ERRORS = (
    ("no longer valid", InvitationNotFoundError),
    ("another email address", InvitationEmailMismatchError),
    ("already a member", AlreadyMemberError),
)


def accept_invitation(db: Session, *, token: str) -> OrganizationMembership:
    """Join the organization of the invitation that matches this token.

    Runs app_private.accept_invitation, which checks the token, its expiry
    and that it was sent to the authenticated user's e-mail.
    """
    try:
        membership_id = db.scalar(
            text("SELECT app_private.accept_invitation(:token)"),
            {"token": token},
        )
    except DBAPIError as exc:
        message = str(exc.orig)
        for fragment, error in _ACCEPT_ERRORS:
            if fragment in message:
                raise error(fragment) from exc
        raise

    return db.get(OrganizationMembership, membership_id)
