from collections.abc import Callable, Sequence
import uuid

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.authentication import get_current_user
from app.db.context import set_organization_context
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.models.user import User


def get_current_membership(
    organization_id: uuid.UUID = Path(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationMembership:
    statement = select(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.user_id == current_user.id,
        OrganizationMembership.is_active.is_(True),
    )

    membership = db.scalar(statement)

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found.",
        )

    set_organization_context(
        db,
        organization_id=membership.organization_id,
    )

    return membership


def require_roles(
    allowed_roles: Sequence[str],
) -> Callable[..., OrganizationMembership]:
    if not allowed_roles:
        raise ValueError("At least one allowed role must be provided")

    valid_roles = {"owner", "admin", "member", "viewer"}
    allowed_roles_set = frozenset(allowed_roles)

    if not allowed_roles_set.issubset(valid_roles):
        raise ValueError("One or more membership roles are invalid")

    def role_dependency(
        membership: OrganizationMembership = Depends(
            get_current_membership
        ),
    ) -> OrganizationMembership:
        if membership.role not in allowed_roles_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient organization permissions.",
            )

        return membership

    return role_dependency
