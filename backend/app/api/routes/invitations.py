import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.authentication import get_current_user
from app.api.dependencies.authorization import require_roles
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.models.user import User
from app.schemas.invitation import (
    InvitationAccept,
    InvitationCreate,
    InvitationCreatedResponse,
    InvitationResponse,
)
from app.schemas.membership import MembershipResponse
from app.services.invitation_service import (
    AlreadyMemberError,
    InvitationAlreadyPendingError,
    InvitationEmailMismatchError,
    InvitationNotFoundError,
    accept_invitation,
    create_invitation,
    list_pending_invitations,
    revoke_invitation,
)
from app.services.membership_service import MembershipPermissionError


organization_router = APIRouter(
    prefix="/organizations/{organization_id}/invitations",
    tags=["Invitations"],
)

invitation_router = APIRouter(
    prefix="/invitations",
    tags=["Invitations"],
)

FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Insufficient organization permissions.",
)


@organization_router.post(
    "/",
    response_model=InvitationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create(
    organization_id: uuid.UUID,
    data: InvitationCreate,
    actor: OrganizationMembership = Depends(
        require_roles(["owner", "admin"])
    ),
    db: Session = Depends(get_db),
):
    try:
        invitation, token = create_invitation(
            db,
            organization_id=organization_id,
            actor_user_id=actor.user_id,
            email=data.email,
            role=data.role,
        )
        db.commit()
        db.refresh(invitation)

    except MembershipPermissionError:
        db.rollback()
        raise FORBIDDEN from None

    except InvitationAlreadyPendingError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An invitation is already pending for this email.",
        ) from None

    return InvitationCreatedResponse(
        **InvitationResponse.model_validate(invitation).model_dump(),
        token=token,
    )


@organization_router.get("/", response_model=list[InvitationResponse])
def list_pending(
    organization_id: uuid.UUID,
    actor: OrganizationMembership = Depends(
        require_roles(["owner", "admin"])
    ),
    db: Session = Depends(get_db),
):
    return list_pending_invitations(db, organization_id=organization_id)


@organization_router.delete(
    "/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def revoke(
    organization_id: uuid.UUID,
    invitation_id: uuid.UUID,
    actor: OrganizationMembership = Depends(
        require_roles(["owner", "admin"])
    ),
    db: Session = Depends(get_db),
):
    try:
        revoke_invitation(
            db,
            organization_id=organization_id,
            actor_user_id=actor.user_id,
            invitation_id=invitation_id,
        )
        db.commit()

    except MembershipPermissionError:
        db.rollback()
        raise FORBIDDEN from None

    except InvitationNotFoundError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found.",
        ) from None

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@invitation_router.post("/accept", response_model=MembershipResponse)
def accept(
    data: InvitationAccept,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        membership = accept_invitation(db, token=data.token)
        db.commit()
        db.refresh(membership)

    except InvitationNotFoundError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found or no longer valid.",
        ) from None

    except InvitationEmailMismatchError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation was sent to another email address.",
        ) from None

    except AlreadyMemberError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already a member of this organization.",
        ) from None

    return membership
