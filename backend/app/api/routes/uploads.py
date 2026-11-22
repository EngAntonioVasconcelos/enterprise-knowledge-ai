import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.authentication import get_current_user
from app.api.dependencies.authorization import require_roles
from app.core.errors import DomainError, NotFoundError
from app.db.session import get_db
from app.models.data_connection import DataConnection
from app.models.membership import OrganizationMembership
from app.models.user import User
from app.schemas.upload import UploadResponse, UploadSourceResponse
from app.services.connection_service import get_connection
from app.services.text_extraction import MAX_FILE_BYTES
from app.services.upload_service import (
    UploadTooLargeError,
    create_upload,
    delete_upload,
    list_my_uploads,
)


router = APIRouter(
    prefix="/organizations/{organization_id}/connections/{connection_id}/uploads",
    tags=["Uploads"],
)

# Viewers read; they do not add content.
UPLOADERS = require_roles(["owner", "admin", "member"])


@router.post(
    "/",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload(
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    file: UploadFile = File(...),
    visibility: str = Form("organization"),
    # With visibility "people": who else may read the file (AL-8b).
    readers: list[uuid.UUID] = Form(default_factory=list),
    member: OrganizationMembership = Depends(UPLOADERS),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Read one byte past the limit, never the whole of a huge request.
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise UploadTooLargeError("The file is larger than 20 MB")

    try:
        connection = get_connection(
            db, organization_id=organization_id, connection_id=connection_id
        )
        created = create_upload(
            db,
            connection=connection,
            user_id=current_user.id,
            user_email=current_user.email,
            filename=file.filename,
            data=data,
            visibility=visibility,
            uploader_role=member.role,
            readers=readers,
        )
        db.commit()
    except DomainError:
        db.rollback()
        raise

    db.refresh(created)
    return created


@router.get("/", response_model=list[UploadResponse])
def list_mine(
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    member: OrganizationMembership = Depends(UPLOADERS),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The caller's own uploads: file names can be telling."""
    return list_my_uploads(
        db, connection_id=connection_id, user_id=current_user.id
    )


@router.delete(
    "/{upload_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def remove(
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    upload_id: uuid.UUID,
    member: OrganizationMembership = Depends(UPLOADERS),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        connection = get_connection(
            db, organization_id=organization_id, connection_id=connection_id
        )
        delete_upload(
            db,
            connection=connection,
            upload_id=upload_id,
            user_id=current_user.id,
        )
        db.commit()
    except DomainError:
        db.rollback()
        raise

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Members may upload but not list connections: this tells them, and only
# them, where the organization's uploaded files go (AL-8a). Owners and
# admins create the source with the first upload.
sources_router = APIRouter(
    prefix="/organizations/{organization_id}/upload-source",
    tags=["Uploads"],
)


@sources_router.get("", response_model=UploadSourceResponse)
def upload_source(
    organization_id: uuid.UUID,
    member: OrganizationMembership = Depends(UPLOADERS),
    db: Session = Depends(get_db),
):
    source = db.scalar(
        select(DataConnection)
        .where(
            DataConnection.organization_id == organization_id,
            DataConnection.provider == "file_upload",
            DataConnection.status != "disconnected",
        )
        .order_by(DataConnection.created_at)
        .limit(1)
    )
    if source is None:
        raise NotFoundError("This organization has no upload source yet")
    return source
