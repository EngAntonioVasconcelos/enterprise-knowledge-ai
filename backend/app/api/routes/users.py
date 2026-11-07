
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse

router = APIRouter(
    prefix="/organizations/{organization_id}/users",
    tags=["Users"],
)


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    organization_id: uuid.UUID,
    user_data: UserCreate,
    db: Session = Depends(get_db),
):
    # Verify that the organization exists.
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

    # Check whether the email is already registered in this organization.
    existing_user = db.scalar(
        select(User).where(
            User.organization_id == organization_id,
            User.email == str(user_data.email),
        )
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User email already exists in this organization.",
        )

    # Create the user and associate it with the requested organization.
    user = User(
        organization_id=organization_id,
        email=str(user_data.email),
        full_name=user_data.full_name,
        role=user_data.role,
    )

    db.add(user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User could not be created because of a data conflict.",
        )

    db.refresh(user)

    return user


@router.get(
    "/",
    response_model=list[UserResponse],
)
def list_organization_users(
    organization_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    # Verify that the organization exists.
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

    # Retrieve users belonging only to the requested organization.
    statement = (
        select(User)
        .where(User.organization_id == organization_id)
        .order_by(User.created_at.desc(), User.id)
        .offset(skip)
        .limit(limit)
    )

    users = db.scalars(statement).all()

    return users
@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """
    Retrieve a user by their unique identifier.
    """

    statement = select(User).where(User.id == user_id)

    user = db.scalar(statement)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return user