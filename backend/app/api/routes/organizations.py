from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies.authentication import get_current_user
from app.api.dependencies.authorization import (
    get_current_membership,
    require_roles,
)
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.services.organization_service import (
    create_organization as create_organization_service,
)

router = APIRouter(
    prefix="/organizations",
    tags=["Organizations"],
)


def _is_organization_slug_conflict(exc: IntegrityError) -> bool:
    original_error = exc.orig

    diagnostic = getattr(original_error, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)

    if constraint_name == "ix_organizations_slug":
        return True

    return (
        "UNIQUE constraint failed: organizations.slug"
        in str(original_error)
    )


@router.post(
    "/",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    organization_data: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        organization = create_organization_service(
            db,
            name=organization_data.name,
            slug=organization_data.slug,
            creator_user_id=current_user.id,
        )

        db.commit()
        db.refresh(organization)

        return organization

    except ValueError as exc:
        db.rollback()

        if str(exc) == "Organization slug already exists":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Organization slug already exists.",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization could not be created.",
        ) from exc

    except IntegrityError as exc:
        db.rollback()

        if _is_organization_slug_conflict(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Organization slug already exists.",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred.",
        ) from exc

    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred.",
        ) from exc


@router.get(
    "/",
    response_model=list[OrganizationResponse],
)
def list_organizations(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    statement = (
        select(Organization)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Organization.id,
        )
        .where(
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.is_active.is_(True),
        )
        .order_by(
            Organization.created_at.desc(),
            Organization.id,
        )
        .offset(skip)
        .limit(limit)
    )

    return db.scalars(statement).all()


@router.get(
    "/{organization_id}",
    response_model=OrganizationResponse,
)
def get_organization(
    organization_id: UUID,
    membership: OrganizationMembership = Depends(get_current_membership),
):
    return membership.organization


@router.patch(
    "/{organization_id}",
    response_model=OrganizationResponse,
)
def update_organization(
    organization_data: OrganizationUpdate,
    membership: OrganizationMembership = Depends(
        require_roles(["owner", "admin"])
    ),
    db: Session = Depends(get_db),
):
    organization = membership.organization

    update_data = organization_data.model_dump(exclude_unset=True)

    if not update_data or any(
        value is None for value in update_data.values()
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="At least one valid field must be provided.",
        )

    if "slug" in update_data:
        normalized_slug = update_data["slug"]

        if len(normalized_slug) < 2:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Slug must contain at least 2 characters.",
            )

        existing_organization = db.scalar(
            select(Organization).where(
                Organization.slug == normalized_slug,
                Organization.id != organization.id,
            )
        )

        if existing_organization is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Organization slug already exists.",
            )

    for field, value in update_data.items():
        setattr(organization, field, value)

    try:
        db.commit()
        db.refresh(organization)

        return organization

    except IntegrityError as exc:
        db.rollback()

        if _is_organization_slug_conflict(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Organization slug already exists.",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred.",
        ) from exc

    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred.",
        ) from exc
