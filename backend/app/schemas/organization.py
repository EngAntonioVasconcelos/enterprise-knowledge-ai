import uuid
from datetime import datetime
from typing import Literal

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
    # Days each person's questions are kept; 0 keeps none.
    history_retention_days: int = 90
    # Limits of the agent for one answer: model calls and tool calls.
    agent_max_steps: int = 5
    agent_max_tool_calls: int = 6

    model_config = ConfigDict(from_attributes=True)


class OrganizationListItem(OrganizationResponse):
    """An organization in the caller's list, with the caller's own role.

    The web app shows management screens (people, sources) only to owners
    and admins; the backend still checks every request.
    """

    role: str


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
    history_retention_days: Literal[0, 30, 90, 365] | None = None
    agent_max_steps: int | None = Field(default=None, ge=1, le=8)
    agent_max_tool_calls: int | None = Field(default=None, ge=1, le=12)

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
