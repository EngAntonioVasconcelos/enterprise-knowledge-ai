
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, InvalidInputError, NotFoundError

from app.models.organization import Organization
from app.models.user import User
from app.services.membership_service import (
    create_initial_owner_membership,
)


def create_organization(
    db: Session,
    *,
    name: str,
    slug: str,
    creator_user_id: uuid.UUID,
) -> Organization:
    normalized_name = name.strip()
    normalized_slug = slug.strip().lower()

    if not normalized_name:
        raise InvalidInputError("Organization name cannot be empty")

    if not normalized_slug:
        raise InvalidInputError("Organization slug cannot be empty")

    # Validate the creator before creating the organization.
    creator = db.get(User, creator_user_id)

    if creator is None:
        raise NotFoundError("User not found")

    if not creator.is_active:
        raise ConflictError("Cannot add an inactive user")

    # Check whether the organization slug is already in use.
    existing_organization = db.scalar(
        select(Organization).where(
            Organization.slug == normalized_slug
        )
    )

    if existing_organization is not None:
        raise ConflictError("Organization slug already exists")

    # Create the organization.
    organization = Organization(
        name=normalized_name,
        slug=normalized_slug,
        created_by_user_id=creator.id,
    )

    db.add(organization)
    db.flush()

    # Assign the creator as the initial organization owner.
    create_initial_owner_membership(
        db,
        organization_id=organization.id,
        user_id=creator.id,
    )

    return organization
