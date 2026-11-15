import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_roles
from app.db.session import get_db
from app.models.document import Document
from app.models.membership import OrganizationMembership
from app.schemas.document import DocumentResponse, DocumentStatistics
from app.services.document_permission_service import (
    document_statistics,
    list_documents,
)


router = APIRouter(
    prefix="/organizations/{organization_id}/documents",
    tags=["Documents"],
)

MEMBERS = require_roles(["owner", "admin", "member", "viewer"])
MANAGERS = require_roles(["owner", "admin"])


@router.get("/", response_model=list[DocumentResponse])
def list_readable(
    organization_id: uuid.UUID,
    member: OrganizationMembership = Depends(MEMBERS),
    db: Session = Depends(get_db),
):
    """Only the documents the caller could open at the source."""
    return list_documents(db, organization_id=organization_id)


@router.get("/statistics", response_model=DocumentStatistics)
def statistics(
    organization_id: uuid.UUID,
    manager: OrganizationMembership = Depends(MANAGERS),
    db: Session = Depends(get_db),
):
    return document_statistics(db, organization_id=organization_id)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_readable(
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    member: OrganizationMembership = Depends(MEMBERS),
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)

    # Not found and not allowed look the same: no hint that it exists.
    if document is None or document.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    return document
