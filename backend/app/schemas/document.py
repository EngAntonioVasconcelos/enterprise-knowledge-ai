import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    connection_id: uuid.UUID
    title: str
    mime_type: str | None = None
    status: str
    current_version_id: uuid.UUID | None = None
    last_synced_at: datetime | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class DocumentStatistics(BaseModel):
    total: int
    by_status: dict[str, int]

    model_config = ConfigDict(extra="forbid")
