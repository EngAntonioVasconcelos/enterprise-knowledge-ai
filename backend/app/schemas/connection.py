import json
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_SETTINGS_BYTES = 16_384

# Settings are stored in clear and shown to admins. Anything that looks like
# a secret is refused here: credentials go to the encrypted store only.
SECRET_WORDS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
)


def _secret_like_keys(value: Any, path: str = "") -> list[str]:
    found = []

    if isinstance(value, dict):
        for key, item in value.items():
            name = f"{path}.{key}" if path else str(key)
            normalized = str(key).lower().replace("-", "_")
            if any(word in normalized for word in SECRET_WORDS):
                found.append(name)
            found.extend(_secret_like_keys(item, name))

    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_secret_like_keys(item, f"{path}[{index}]"))

    return found


def _validate_settings(value: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(value)) > MAX_SETTINGS_BYTES:
        raise ValueError(
            f"settings must be at most {MAX_SETTINGS_BYTES} bytes"
        )

    secret_keys = _secret_like_keys(value)
    if secret_keys:
        raise ValueError(
            "settings must not contain credentials "
            f"({', '.join(secret_keys)}); they are stored encrypted, apart"
        )

    return value


def _clean_name(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError("name must not be empty")
    return value


class ConnectionCreate(BaseModel):
    provider: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    settings: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean_name(value)

    @field_validator("settings")
    @classmethod
    def check_settings(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_settings(value)


class ConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    # Disconnecting has its own route: it is final.
    status: Literal["active", "paused"] | None = None
    settings: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)

    @field_validator("settings")
    @classmethod
    def check_settings(cls, value: dict[str, Any] | None):
        return None if value is None else _validate_settings(value)


class ConnectionResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    kind: str
    provider: str
    name: str
    status: str
    settings: dict[str, Any]
    last_synced_at: datetime | None = None
    last_error: str | None = None
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    disconnected_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")
