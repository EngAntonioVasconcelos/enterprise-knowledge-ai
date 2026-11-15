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
