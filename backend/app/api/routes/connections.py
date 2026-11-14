import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_roles
from app.core.errors import DomainError
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.schemas.connection import (
    ConnectionCreate,
    ConnectionResponse,
    ConnectionUpdate,
)
from app.services.connection_service import (
    create_connection,
    disconnect_connection,
    get_connection,
    list_connections,
    update_connection,
)


router = APIRouter(
    prefix="/organizations/{organization_id}/connections",
    tags=["Connections"],
)

MANAGERS = require_roles(["owner", "admin"])


@router.get("/", response_model=list[ConnectionResponse])
def list_all(
    organization_id: uuid.UUID,
    include_disconnected: bool = Query(default=False),
    manager: OrganizationMembership = Depends(MANAGERS),
    db: Session = Depends(get_db),
):
    return list_connections(
        db,
        organization_id=organization_id,
        include_disconnected=include_disconnected,
    )


@router.post(
    "/",
    response_model=ConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create(
    organization_id: uuid.UUID,
    data: ConnectionCreate,
    manager: OrganizationMembership = Depends(MANAGERS),
    db: Session = Depends(get_db),
):
    try:
        connection = create_connection(
            db,
            organization_id=organization_id,
            actor_user_id=manager.user_id,
            provider=data.provider,
            name=data.name,
            settings=data.settings,
        )
        db.commit()
    except DomainError:
        db.rollback()
        raise

    db.refresh(connection)
    return connection


@router.get("/{connection_id}", response_model=ConnectionResponse)
def get_one(
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    manager: OrganizationMembership = Depends(MANAGERS),
    db: Session = Depends(get_db),
):
    return get_connection(
        db, organization_id=organization_id, connection_id=connection_id
    )


@router.patch("/{connection_id}", response_model=ConnectionResponse)
def update(
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    data: ConnectionUpdate,
    manager: OrganizationMembership = Depends(MANAGERS),
    db: Session = Depends(get_db),
):
    try:
        connection = update_connection(
            db,
            organization_id=organization_id,
            connection_id=connection_id,
            name=data.name,
            status=data.status,
            settings=data.settings,
        )
        db.commit()
    except DomainError:
        db.rollback()
        raise

    db.refresh(connection)
    return connection


@router.post(
    "/{connection_id}/disconnect",
    response_model=ConnectionResponse,
)
def disconnect(
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    manager: OrganizationMembership = Depends(MANAGERS),
    db: Session = Depends(get_db),
):
    try:
        connection = disconnect_connection(
            db,
            organization_id=organization_id,
            connection_id=connection_id,
        )
        db.commit()
    except DomainError:
        db.rollback()
        raise

    db.refresh(connection)
    return connection
