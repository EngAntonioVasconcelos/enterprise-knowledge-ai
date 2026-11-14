
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ForbiddenError, InvalidInputError, NotFoundError

from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.user import User


ALLOWED_ROLES = {"owner", "admin", "member", "viewer"}

class MembershipPermissionError(ForbiddenError):
    """Raised when an actor lacks permission to manage memberships."""


def _validate_role(role: str) -> None:
    if role not in ALLOWED_ROLES:
        raise InvalidInputError(f"Invalid membership role: {role}")


def _lock_organization(
    db: Session,
    organization_id: uuid.UUID,
) -> Organization:
    statement = (
        select(Organization)
        .where(Organization.id == organization_id)
        .with_for_update()
    )

    organization = db.scalar(statement)

    if organization is None:
        raise NotFoundError("Organization not found")

    return organization


def _get_authorized_actor_membership(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    allowed_roles: set[str],
) -> OrganizationMembership:
    statement = (
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == actor_user_id,
            OrganizationMembership.is_active.is_(True),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )

    actor_membership = db.scalar(statement)

    if actor_membership is None:
        raise NotFoundError(
            "Actor is not an active member of the organization"
        )

    if actor_membership.role not in allowed_roles:
     raise MembershipPermissionError(
        "Insufficient organization permissions"
    )

    return actor_membership


def _ensure_another_active_owner_exists(
    db: Session,
    membership: OrganizationMembership,
) -> None:
    statement = select(func.count()).select_from(
        OrganizationMembership
    ).where(
        OrganizationMembership.organization_id
        == membership.organization_id,
        OrganizationMembership.role == "owner",
        OrganizationMembership.is_active.is_(True),
        OrganizationMembership.id != membership.id,
    )

    active_owners = db.scalar(statement) or 0

    if active_owners == 0:
        raise ConflictError(
            "Cannot remove or demote the last active owner"
        )


def _lock_organization_for_bootstrap(
    db: Session,
    organization_id: uuid.UUID,
) -> Organization:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("""
                SELECT pg_catalog.pg_advisory_xact_lock(
                    pg_catalog.hashtextextended(
                        CAST(:organization_id AS text),
                        0
                    )
                )
            """),
            {"organization_id": str(organization_id)},
        )

    organization = db.scalar(
        select(Organization).where(
            Organization.id == organization_id
        )
    )

    if organization is None:
        raise NotFoundError("Organization not found")

    return organization

def create_initial_owner_membership(
    db: Session,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> OrganizationMembership:
    _lock_organization_for_bootstrap(db, organization_id)

    user = db.get(User, user_id)

    if user is None:
        raise NotFoundError("User not found")

    if not user.is_active:
        raise ConflictError("Cannot add an inactive user")

    existing_membership = db.scalar(
        select(OrganizationMembership.id)
        .where(
            OrganizationMembership.organization_id == organization_id
        )
        .limit(1)
    )

    if existing_membership is not None:
        raise ConflictError(
            "Initial owner membership can only be created "
            "for an organization without existing memberships"
        )

    membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=user_id,
        role="owner",
        has_held_privileged_role=True,
        has_held_owner_role=True,
        is_active=True,
    )

    db.add(membership)
    db.flush()

    return membership


def create_membership(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str = "member",
) -> OrganizationMembership:
    _validate_role(role)

    _lock_organization(db, organization_id)

    statement = (
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )

    existing = db.scalar(statement)

    requires_owner = role in {"owner", "admin"}

    if existing is not None:
        requires_owner = (
            requires_owner
            or existing.has_held_privileged_role
        )

    allowed_actor_roles = (
        {"owner"} if requires_owner else {"owner", "admin"}
    )

    _get_authorized_actor_membership(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        allowed_roles=allowed_actor_roles,
    )

    user = db.get(User, user_id)

    if user is None:
        raise NotFoundError("User not found")

    if not user.is_active:
        raise ConflictError("Cannot add an inactive user")

    if existing is not None:
        if existing.is_active:
            raise ConflictError("Membership already exists")

        if role == "owner":
            _ensure_another_active_owner_exists(db, existing)

        existing.role = role
        existing.has_held_privileged_role = (
            existing.has_held_privileged_role
            or role in {"owner", "admin"}
        )
        existing.has_held_owner_role = (
            existing.has_held_owner_role or role == "owner"
        )
        existing.is_active = True
        db.flush()
        return existing

    membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=user_id,
        role=role,
        has_held_privileged_role=role in {"owner", "admin"},
        has_held_owner_role=role == "owner",
        is_active=True,
    )

    db.add(membership)
    db.flush()

    return membership


def get_membership(
    db: Session,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> OrganizationMembership | None:
    statement = select(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.user_id == user_id,
    )

    return db.scalar(statement)


def list_organization_memberships(
    db: Session,
    *,
    organization_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> list[OrganizationMembership]:
    statement = (
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.is_active.is_(True),
        )
        .order_by(
            OrganizationMembership.created_at,
            OrganizationMembership.id,
        )
        .offset(skip)
        .limit(limit)
    )

    return list(db.scalars(statement).all())



def update_membership_role(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
) -> OrganizationMembership:
    _validate_role(role)

    _lock_organization(db, organization_id)

    actor_membership = _get_authorized_actor_membership(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        allowed_roles={"owner", "admin"},
    )

    statement = (
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )

    target_membership = db.scalar(statement)

    if target_membership is None:
        raise NotFoundError("Membership not found")

    if not target_membership.is_active:
        raise ConflictError("Cannot update an inactive membership")

    requires_owner = (
        target_membership.has_held_privileged_role
        or role in {"owner", "admin"}
    )

    if requires_owner and actor_membership.role != "owner":
        raise MembershipPermissionError(
            "Only an owner can manage owner or admin memberships"
        )

    if target_membership.role == "owner" and role != "owner":
        _ensure_another_active_owner_exists(
            db,
            target_membership,
        )

    target_membership.role = role
    target_membership.has_held_privileged_role = (
        target_membership.has_held_privileged_role
        or role in {"owner", "admin"}
    )
    target_membership.has_held_owner_role = (
        target_membership.has_held_owner_role or role == "owner"
    )
    db.flush()

    return target_membership



def deactivate_membership(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    user_id: uuid.UUID,
) -> OrganizationMembership:
    _lock_organization(db, organization_id)

    actor_membership = _get_authorized_actor_membership(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        allowed_roles={"owner", "admin"},
    )

    statement = (
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )

    target_membership = db.scalar(statement)

    if target_membership is None:
        raise NotFoundError("Membership not found")

    if (
        actor_membership.role != "owner"
        and target_membership.has_held_privileged_role
    ):
        raise MembershipPermissionError(
            "Only an owner can deactivate owner or admin memberships"
        )

    if not target_membership.is_active:
        return target_membership

    if target_membership.role == "owner":
        _ensure_another_active_owner_exists(
            db,
            target_membership,
        )

    target_membership.is_active = False
    db.flush()

    return target_membership
