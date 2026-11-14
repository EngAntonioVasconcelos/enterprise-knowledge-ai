import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_roles
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.schemas.directory import DirectoryEntry
from app.services.directory_service import list_directory


router = APIRouter(
    prefix="/organizations/{organization_id}/directory",
    tags=["Directory"],
)


@router.get("/", response_model=list[DirectoryEntry])
def list_colleagues(
    organization_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    member: OrganizationMembership = Depends(
        require_roles(["owner", "admin", "member"])
    ),
    db: Session = Depends(get_db),
):
    return list_directory(
        db,
        organization_id=organization_id,
        skip=skip,
        limit=limit,
    )
