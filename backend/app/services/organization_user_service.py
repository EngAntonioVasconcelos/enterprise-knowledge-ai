
import uuid

from sqlalchemy.orm import Session

from app.models.membership import OrganizationMembership
from app.models.user import User
from app.services.membership_service import create_membership
from app.services.user_service import create_user, get_user_by_email


def create_organization_user(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    email: str,
    full_name: str,
    role: str = "member",
) -> tuple[User, OrganizationMembership]:
    """
    Create or reuse a global user and associate them with an organization.
    """

    user = get_user_by_email(db, email)

    if user is None:
        user = create_user(
            db,
            email=email,
            full_name=full_name,
        )

    elif not user.is_active:
        raise ValueError("Cannot add an inactive user")

    membership = create_membership(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        user_id=user.id,
        role=role,
    )

    return user, membership
