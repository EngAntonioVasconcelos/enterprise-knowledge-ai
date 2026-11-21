import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_roles
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.schemas.answer import AnswerSourceResponse
from app.schemas.history import HistoryEntry, HistoryItem
from app.services import history_service


router = APIRouter(
    prefix="/organizations/{organization_id}/history",
    tags=["History"],
)

MEMBERS = require_roles(["owner", "admin", "member", "viewer"])

NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Question not found.",
)


@router.get("/", response_model=list[HistoryItem])
def list_history(
    organization_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    member: OrganizationMembership = Depends(MEMBERS),
    db: Session = Depends(get_db),
):
    """The caller's own questions, newest first. Nobody else's."""
    return history_service.list_entries(
        db,
        organization=member.organization,
        user_id=member.user_id,
        limit=limit,
    )


@router.get("/{entry_id}", response_model=HistoryEntry)
def open_history_entry(
    organization_id: uuid.UUID,
    entry_id: uuid.UUID,
    member: OrganizationMembership = Depends(MEMBERS),
    db: Session = Depends(get_db),
):
    opened = history_service.open_entry(
        db,
        organization=member.organization,
        user_id=member.user_id,
        entry_id=entry_id,
    )
    if opened is None:
        raise NOT_FOUND
    entry = opened.entry
    return HistoryEntry(
        id=entry.id,
        question=entry.question,
        answer=opened.answer,
        abstained=entry.abstained,
        verified=entry.verified,
        language=entry.language,
        created_at=entry.created_at,
        sources=[AnswerSourceResponse(**source) for source in opened.sources],
        hidden=opened.hidden,
        outdated=opened.outdated,
    )


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_history_entry(
    organization_id: uuid.UUID,
    entry_id: uuid.UUID,
    member: OrganizationMembership = Depends(MEMBERS),
    db: Session = Depends(get_db),
):
    deleted = history_service.delete_entry(
        db,
        organization_id=organization_id,
        user_id=member.user_id,
        entry_id=entry_id,
    )
    if not deleted:
        db.rollback()
        raise NOT_FOUND
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_history(
    organization_id: uuid.UUID,
    member: OrganizationMembership = Depends(MEMBERS),
    db: Session = Depends(get_db),
):
    history_service.delete_all(
        db, organization_id=organization_id, user_id=member.user_id
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
