import uuid
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class OrganizationCreate(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=150,
    )
    slug: str = Field(
        min_length=2,
        max_length=100,
    )

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        if isinstance(value, str):
            value = value.strip()

        return value

    @field_validator("slug", mode="before")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        if isinstance(value, str):
            value = value.strip().lower()

        return value


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=150,
    )
    slug: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            value = value.strip()

        return value

    @field_validator("slug", mode="before")
    @classmethod
    def normalize_slug(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            value = value.strip().lower()

        return value
