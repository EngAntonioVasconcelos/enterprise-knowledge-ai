
import pytest
from pydantic import ValidationError

from app.schemas.user import (
    UserCreate,
    UserUpdate,
)


def test_create_user_with_valid_data():
    user = UserCreate(
        email="employee@example.com",
        full_name="John Smith",
    )

    assert user.email == "employee@example.com"
    assert user.full_name == "John Smith"
    assert user.role == "member"


def test_create_user_with_admin_role():
    user = UserCreate(
        email="admin@example.com",
        full_name="Organization Admin",
        role="admin",
    )

    assert user.role == "admin"


def test_create_user_rejects_invalid_email():
    with pytest.raises(ValidationError):
        UserCreate(
            email="invalid-email",
            full_name="John Smith",
        )


def test_create_user_rejects_invalid_role():
    with pytest.raises(ValidationError):
        UserCreate(
            email="employee@example.com",
            full_name="John Smith",
            role="superadmin",
        )


def test_update_user_with_partial_data():
    user = UserUpdate(
        full_name="Updated Name",
    )

    update_data = user.model_dump(exclude_unset=True)

    assert update_data == {
        "full_name": "Updated Name"
    }


def test_update_user_rejects_invalid_role():
    with pytest.raises(ValidationError):
        UserUpdate(role="superadmin")
