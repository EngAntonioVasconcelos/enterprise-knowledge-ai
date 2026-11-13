
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserCreate, UserResponse


MembershipRole = Literal[
    "owner",
    "admin",
    "member",
    "viewer",
]


class MembershipCreate(BaseModel):
    role: MembershipRole = "member"

    model_config = ConfigDict(extra="forbid")


class MembershipUpdate(BaseModel):
    role: MembershipRole | None = None

    model_config = ConfigDict(extra="forbid")


class OrganizationUserCreate(UserCreate):
    role: MembershipRole = "member"

    model_config = ConfigDict(extra="forbid")


class MembershipResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: MembershipRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class OrganizationUserResponse(UserResponse):
    membership: MembershipResponse
