import uuid

from pydantic import BaseModel, ConfigDict

from app.schemas.membership import MembershipRole


class DirectoryEntry(BaseModel):
    """A colleague as other members see them: no e-mail address."""

    user_id: uuid.UUID
    full_name: str
    role: MembershipRole

    model_config = ConfigDict(extra="forbid")
