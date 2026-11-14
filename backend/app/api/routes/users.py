
import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import (
    get_current_membership,
    require_roles,
)
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.schemas.membership import (
    MembershipResponse,
    MembershipUpdate,
    OrganizationUserResponse,
)
from app.services.membership_service import (
    MembershipPermissionError,
    deactivate_membership,
    get_membership,
    list_organization_memberships,
    update_membership_role,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/users",
    tags=["Users"],
)


def _build_organization_user_response(
    membership: OrganizationMembership,
) -> OrganizationUserResponse:
    user = membership.user

    return OrganizationUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        membership=membership,
    )



@router.get(
    "/",
    response_model=list[OrganizationUserResponse],
)
def list_organization_users(
    organization_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    current_membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    memberships = list_organization_memberships(
        db,
        organization_id=organization_id,
        skip=skip,
        limit=limit,
    )

    return [
        _build_organization_user_response(membership)
        for membership in memberships
    ]


@router.get(
    "/{user_id}",
    response_model=OrganizationUserResponse,
)
def get_user(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    current_membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    membership = get_membership(
        db,
        organization_id=organization_id,
        user_id=user_id,
    )

    if membership is None or not membership.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return _build_organization_user_response(membership)


@router.patch(
    "/{user_id}/membership",
    response_model=MembershipResponse,
)
def update_user_membership(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    membership_data: MembershipUpdate,
    actor_membership: OrganizationMembership = Depends(
        require_roles(["owner", "admin"])
    ),
    db: Session = Depends(get_db),
):
    update_data = membership_data.model_dump(exclude_unset=True)

    if (
        not update_data
        or update_data.get("role") is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A valid membership role must be provided.",
        )

    target_membership = get_membership(
        db,
        organization_id=organization_id,
        user_id=user_id,
    )

    if (
        target_membership is None
        or not target_membership.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    try:
        updated_membership = update_membership_role(
            db,
            organization_id=organization_id,
            actor_user_id=actor_membership.user_id,
            user_id=user_id,
            role=update_data["role"],
        )

        db.commit()
        db.refresh(updated_membership)

    except MembershipPermissionError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc) + ".",
        ) from exc

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc) + ".",
        ) from exc

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Membership update conflicts with existing data.",
        ) from exc

    return updated_membership



@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_user(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    actor_membership: OrganizationMembership = Depends(
        require_roles(["owner", "admin"])
    ),
    db: Session = Depends(get_db),
):
    target_membership = get_membership(
        db,
        organization_id=organization_id,
        user_id=user_id,
    )

    if target_membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    try:
        deactivate_membership(
            db,
            organization_id=organization_id,
            actor_user_id=actor_membership.user_id,
            user_id=user_id,
        )
        db.commit()

    except MembershipPermissionError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc) + ".",
        ) from exc

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc) + ".",
        ) from exc

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Membership could not be deactivated.",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
