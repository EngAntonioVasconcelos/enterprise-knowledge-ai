import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.organization import Organization
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
)
router = APIRouter(
    prefix="/organizations",
    tags=["Organizations"],
)


@router.post(
    "/",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    organization_data: OrganizationCreate,
    db: Session = Depends(get_db),
):
    # Check whether an organization with this slug already exists.
    existing_organization = db.scalar(
        select(Organization).where(
            Organization.slug == organization_data.slug
        )
    )

    if existing_organization:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists.",
        )

    # Create a new SQLAlchemy model instance.
    organization = Organization(
        name=organization_data.name,
        slug=organization_data.slug,
    )

    # Add the organization to the database session.
    db.add(organization)

    try:
        # Commit the transaction to the database.
        db.commit()

    except IntegrityError:
        # Roll back the transaction if a database conflict occurs.
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists.",
        )

    # Refresh the instance with the persisted database values.
    db.refresh(organization)

    return organization


@router.get(
    "/",
    response_model=list[OrganizationResponse],
)
def list_organizations(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    # Build the query and apply pagination.
    statement = (
        select(Organization)
        .order_by(Organization.created_at.desc(), Organization.id)
        .offset(skip)
        .limit(limit)
    )

    # Execute the query and retrieve all matching organizations.
    organizations = db.scalars(statement).all()

    return organizations

@router.get(
    "/{organization_id}",
    response_model=OrganizationResponse,
)
def get_organization(
    organization_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    # Retrieve the organization by its UUID.
    organization = db.scalar(
        select(Organization).where(
            Organization.id == organization_id
        )
    )

    # Return 404 if the organization does not exist.
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found.",
        )

    return organization

@router.patch(
    "/{organization_id}",
    response_model=OrganizationResponse,
)
def update_organization(
    organization_id: uuid.UUID,
    organization_data: OrganizationUpdate,
    db: Session = Depends(get_db),
):
    # Retrieve the organization by its UUID.
    organization = db.scalar(
        select(Organization).where(
            Organization.id == organization_id
        )
    )

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found.",
        )

    # Extract only the fields explicitly provided by the client.
    update_data = organization_data.model_dump(exclude_unset=True)

    # Reject empty updates and explicit null values.
    if not update_data or any(
        value is None for value in update_data.values()
    ):
      raise HTTPException(
    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    detail="At least one valid field must be provided.",
)

    # Check whether the new slug belongs to another organization.
    if "slug" in update_data:
        existing_organization = db.scalar(
            select(Organization).where(
                Organization.slug == update_data["slug"],
                Organization.id != organization_id,
            )
        )

        if existing_organization:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Organization slug already exists.",
            )

    # Apply the provided changes.
    for field, value in update_data.items():
        setattr(organization, field, value)

    try:
        # Commit the changes to the database.
        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization update conflicts with existing data.",
        )

    # Refresh the organization with the updated database values.
    db.refresh(organization)

    return organization

