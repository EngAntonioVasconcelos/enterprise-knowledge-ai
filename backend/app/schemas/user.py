

import uuid
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(
        min_length=2,
        max_length=150,
    )
    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()
    model_config = ConfigDict(extra="forbid")


class UserUpdate(BaseModel):
    full_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=150,
    )
    is_active: bool | None = None

    model_config = ConfigDict(extra="forbid")


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )
