import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


MAX_SECRET_BYTES = 16_384


class CredentialsUpdate(BaseModel):
    # Whatever the provider needs (a refresh token, a database user and
    # password...). It is sealed at once and never returned.
    secret: dict[str, Any]

    model_config = ConfigDict(extra="forbid")

    @field_validator("secret")
    @classmethod
    def check_secret(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("secret must not be empty")
        if len(json.dumps(value)) > MAX_SECRET_BYTES:
            raise ValueError(
                f"secret must be at most {MAX_SECRET_BYTES} bytes"
            )
        return value

    def __repr__(self) -> str:
        # Never let a secret reach a log through a repr.
        return "CredentialsUpdate(secret=<hidden>)"

    __str__ = __repr__


class CredentialsStatus(BaseModel):
    configured: bool
    updated_at: datetime | None = None
    key: str | None = None

    model_config = ConfigDict(extra="forbid")
