import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


InvitationRole = Literal["owner", "admin", "member", "viewer"]
InvitationStatus = Literal["pending", "accepted", "revoked", "expired"]


class InvitationCreate(BaseModel):
    email: EmailStr
    role: InvitationRole = "member"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    model_config = ConfigDict(extra="forbid")


class InvitationResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    role: InvitationRole
    status: InvitationStatus
    invited_by_user_id: uuid.UUID
    expires_at: datetime
    created_at: datetime
    accepted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class InvitationCreatedResponse(InvitationResponse):
    # Shown once. Only its hash is stored, so it cannot be retrieved later.
    token: str


class InvitationAccept(BaseModel):
    token: str = Field(min_length=20, max_length=200)

    model_config = ConfigDict(extra="forbid")
