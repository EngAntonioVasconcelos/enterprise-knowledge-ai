import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    id: int
    action: str
    target_type: str
    target_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    details: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")
