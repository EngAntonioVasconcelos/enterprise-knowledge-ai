
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


UserRole = Literal["admin", "member"]


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(
        min_length=2,
        max_length=150,
    )
    role: UserRole = "member"


class UserUpdate(BaseModel):
    full_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=150,
    )
    role: UserRole | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
