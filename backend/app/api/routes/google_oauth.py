import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_roles
from app.core.errors import DomainError
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.schemas.credential import CredentialsStatus
from app.schemas.google_oauth import (
    GoogleAuthorizationCallback,
    GoogleAuthorizationStart,
)
from app.services.connection_service import get_connection
from app.services.credential_service import credentials_status
from app.services.google_oauth import authorization_url, complete_authorization


router = APIRouter(
    prefix="/organizations/{organization_id}/connections/{connection_id}/google",
    tags=["Connections"],
)

MANAGERS = require_roles(["owner", "admin"])


@router.post("/authorize", response_model=GoogleAuthorizationStart)
def authorize(
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    manager: OrganizationMembership = Depends(MANAGERS),
    db: Session = Depends(get_db),
):
    """The Google address to open; it works for this person, for 10 minutes."""
    connection = get_connection(
        db, organization_id=organization_id, connection_id=connection_id
    )
    return GoogleAuthorizationStart(
        authorization_url=authorization_url(
            connection=connection, user_id=manager.user_id
        )
    )


@router.post("/callback", response_model=CredentialsStatus)
def callback(
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    data: GoogleAuthorizationCallback,
    manager: OrganizationMembership = Depends(MANAGERS),
    db: Session = Depends(get_db),
):
    """Finish the authorization: the token is sealed, never returned."""
    try:
        connection = get_connection(
            db, organization_id=organization_id, connection_id=connection_id
        )
        complete_authorization(
            db,
            connection=connection,
            user_id=manager.user_id,
            code=data.code,
            state=data.state,
        )
        db.commit()
    except DomainError:
        db.rollback()
        raise

    return credentials_status(
        db, organization_id=organization_id, connection_id=connection_id
    )
