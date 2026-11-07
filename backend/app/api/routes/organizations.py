
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.organization import Organization
from app.schemas.organization import OrganizationCreate, OrganizationResponse


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

