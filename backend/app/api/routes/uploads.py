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
from sqlalchemy.orm import Session

from app.api.dependencies.authentication import get_current_user
from app.api.dependencies.authorization import require_roles
from app.core.errors import DomainError
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.models.user import User
from app.schemas.upload import UploadResponse
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
