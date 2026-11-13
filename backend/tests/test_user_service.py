
import uuid

import pytest

from app.models.user import User
from app.services.user_service import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    update_user,
)


def test_create_user(db_session):
    user = create_user(
        db_session,
        email="employee@example.com",
        full_name="John Smith",
    )

    assert user.id is not None
    assert user.email == "employee@example.com"
    assert user.full_name == "John Smith"
    assert user.is_active is True

    assert db_session.query(User).count() == 1


def test_create_user_normalizes_email(db_session):
    user = create_user(
        db_session,
        email="  USER@EXAMPLE.COM  ",
        full_name="John Smith",
    )

    assert user.email == "user@example.com"


def test_get_user_by_email(db_session):
    user = create_user(
        db_session,
        email="employee@example.com",
        full_name="John Smith",
    )

    result = get_user_by_email(
        db_session,
        "EMPLOYEE@EXAMPLE.COM",
    )

    assert result is not None
    assert result.id == user.id


def test_get_user_by_email_returns_none_when_not_found(db_session):
    result = get_user_by_email(
        db_session,
        "unknown@example.com",
    )

    assert result is None


def test_get_user_by_id(db_session):
    user = create_user(
        db_session,
        email="employee@example.com",
        full_name="John Smith",
    )

    result = get_user_by_id(db_session, user.id)

    assert result is not None
    assert result.email == "employee@example.com"


def test_get_user_by_id_returns_none_when_not_found(db_session):
    result = get_user_by_id(
        db_session,
        uuid.uuid4(),
    )

    assert result is None


def test_update_user(db_session):
    user = create_user(
        db_session,
        email="employee@example.com",
        full_name="John Smith",
    )

    updated_user = update_user(
        db_session,
        user,
        {"full_name": "John Updated"},
    )

    assert updated_user.full_name == "John Updated"
    assert updated_user.email == "employee@example.com"


def test_update_user_active_status(db_session):
    user = create_user(
        db_session,
        email="employee@example.com",
        full_name="John Smith",
    )

    updated_user = update_user(
        db_session,
        user,
        {"is_active": False},
    )

    assert updated_user.is_active is False


def test_update_user_rejects_unsupported_fields(db_session):
    user = create_user(
        db_session,
        email="employee@example.com",
        full_name="John Smith",
    )

    with pytest.raises(ValueError, match="Unsupported user fields"):
        update_user(
            db_session,
            user,
            {"role": "admin"},
        )

    assert user.full_name == "John Smith"


def test_update_user_ignores_none_values(db_session):
    user = create_user(
        db_session,
        email="employee@example.com",
        full_name="John Smith",
    )

    updated_user = update_user(
        db_session,
        user,
        {"full_name": None},
    )

    assert updated_user.full_name == "John Smith"


def test_create_user_rejects_empty_email(db_session):
    with pytest.raises(ValueError, match="Email cannot be empty"):
        create_user(
            db_session,
            email="   ",
            full_name="John Smith",
        )


def test_create_user_rejects_empty_full_name(db_session):
    with pytest.raises(ValueError, match="Full name cannot be empty"):
        create_user(
            db_session,
            email="employee@example.com",
            full_name="   ",
        )


def test_create_user_normalizes_full_name(db_session):
    user = create_user(
        db_session,
        email="employee@example.com",
        full_name="  John Smith  ",
    )

    assert user.full_name == "John Smith"


def test_get_user_by_email_rejects_empty_email(db_session):
    with pytest.raises(ValueError, match="Email cannot be empty"):
        get_user_by_email(db_session, "   ")


def test_update_user_normalizes_full_name(db_session):
    user = create_user(
        db_session,
        email="employee@example.com",
        full_name="John Smith",
    )

    updated_user = update_user(
        db_session,
        user,
        {"full_name": "  John Updated  "},
    )

    assert updated_user.full_name == "John Updated"


@pytest.mark.parametrize("invalid_value", ["false", 0, 1])
def test_update_user_rejects_non_boolean_active_status(
    db_session,
    invalid_value,
):
    user = create_user(
        db_session,
        email="employee@example.com",
        full_name="John Smith",
    )

    with pytest.raises(ValueError, match="is_active must be a boolean"):
        update_user(
            db_session,
            user,
            {"is_active": invalid_value},
        )

    assert user.is_active is True
