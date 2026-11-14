import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_roles
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.schemas.audit import AuditEventResponse
from app.services.audit_service import list_audit_events


router = APIRouter(
    prefix="/organizations/{organization_id}/audit-events",
    tags=["Audit"],
)


@router.get("/", response_model=list[AuditEventResponse])
def list_events(
    organization_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    manager: OrganizationMembership = Depends(
        require_roles(["owner", "admin"])
    ),
    db: Session = Depends(get_db),
):
    return list_audit_events(
        db,
        organization_id=organization_id,
        skip=skip,
        limit=limit,
    )
