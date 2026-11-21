import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_roles
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.schemas.dashboard import Dashboard
from app.services.dashboard_service import build_dashboard


router = APIRouter(
    prefix="/organizations/{organization_id}/dashboard",
    tags=["Dashboard"],
)


@router.get("/", response_model=Dashboard)
def dashboard(
    organization_id: uuid.UUID,
    manager: OrganizationMembership = Depends(require_roles(["owner", "admin"])),
    db: Session = Depends(get_db),
):
    """The last 30 days in numbers, for owners and admins."""
    return build_dashboard(db, organization_id=organization_id)
