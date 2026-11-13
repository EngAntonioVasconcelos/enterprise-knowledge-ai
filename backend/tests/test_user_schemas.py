import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
)


def test_create_user_with_valid_data():
    user = UserCreate(
        email="employee@example.com",
        full_name="John Smith",
    )

    assert str(user.email) == "employee@example.com"
    assert user.full_name == "John Smith"


def test_create_user_rejects_invalid_email():
    with pytest.raises(ValidationError):
        UserCreate(
            email="invalid-email",
            full_name="John Smith",
        )


def test_create_user_rejects_short_full_name():
    with pytest.raises(ValidationError):
        UserCreate(
            email="employee@example.com",
            full_name="J",
        )


def test_create_user_rejects_organization_id():
    with pytest.raises(ValidationError):
        UserCreate(
            email="employee@example.com",
            full_name="John Smith",
            organization_id=str(uuid.uuid4()),
        )


def test_create_user_rejects_organization_role():
    with pytest.raises(ValidationError):
        UserCreate(
            email="employee@example.com",
            full_name="John Smith",
            role="admin",
        )


def test_update_user_with_partial_data():
    user = UserUpdate(full_name="Updated Name")

    assert user.model_dump(exclude_unset=True) == {
        "full_name": "Updated Name"
    }


def test_update_user_global_active_status():
    user = UserUpdate(is_active=False)

    assert user.model_dump(exclude_unset=True) == {
        "is_active": False
    }


def test_update_user_rejects_role():
    with pytest.raises(ValidationError):
        UserUpdate(role="admin")


def test_user_response_contains_global_identity_fields():
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    user = UserResponse(
        id=user_id,
        email="employee@example.com",
        full_name="John Smith",
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    assert user.id == user_id
    assert str(user.email) == "employee@example.com"
    assert user.full_name == "John Smith"
    assert user.is_active is True
    assert user.created_at == now
    assert user.updated_at == now

    assert "organization_id" not in user.model_dump()
    assert "role" not in user.model_dump()

def test_user_create_normalizes_email():
    user = UserCreate(
        email="USER@EXAMPLE.COM",
        full_name="John Smith",
    )

    assert str(user.email) == "user@example.com"