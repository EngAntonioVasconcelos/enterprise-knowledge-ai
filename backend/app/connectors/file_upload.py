"""The file_upload connector: uploaded files as a source like any other.

Its "source" is the file_uploads table and the stored originals. Every
sync lists all active uploads (a complete listing, so a deleted upload
leaves retrieval), with the upload's SHA-256 as revision: an unchanged
file is never read or parsed again.
"""

from sqlalchemy import select

from app.connectors.base import (
    ChangeSet,
    ConnectionContext,
    SourceItem,
    register_connector,
)
from app.models.file_upload import FileUpload
from app.services.document_permission_service import SourcePermission
from app.services.object_storage import get_object_storage
from app.services.text_extraction import extract_text


def _permissions(upload: FileUpload) -> tuple[SourcePermission, ...]:
    if upload.visibility == "organization":
        return (SourcePermission("organization"),)
    return (SourcePermission("user", upload.uploader_email, "owner"),)


class FileUploadConnector:
    def __init__(self, context: ConnectionContext):
        if context.db is None:
            raise ValueError("The file_upload connector needs a session")
        self.context = context
        self.storage = context.storage or get_object_storage()
        self._keys: dict[str, str] = {}

    def list_changes(self, cursor: str | None) -> ChangeSet:
        uploads = self.context.db.scalars(
            select(FileUpload).where(
                FileUpload.connection_id == self.context.connection_id,
                FileUpload.status == "active",
            )
        ).all()

        items = []
        for upload in uploads:
            self._keys[str(upload.id)] = upload.original_object_key
            items.append(
                SourceItem(
                    external_id=str(upload.id),
                    title=upload.filename,
                    mime_type=upload.mime_type,
                    revision=upload.sha256,
                    modified_at=upload.created_at,
                    permissions=_permissions(upload),
                )
            )

        return ChangeSet(changed=tuple(items), complete=True)

    def fetch_text(self, item: SourceItem) -> str:
        data = self.storage.get(self._keys[item.external_id])
        _, text = extract_text(data)
        return text


@register_connector("file_upload")
def build(context: ConnectionContext) -> FileUploadConnector:
    return FileUploadConnector(context)
