import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UploadResponse(BaseModel):
    id: uuid.UUID
    connection_id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    visibility: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class UploadSourceResponse(BaseModel):
    """Where an organization's uploaded files go: enough to send one."""

    id: uuid.UUID
    name: str
    status: str
    last_synced_at: datetime | None = None
    last_error: str | None = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")
