from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def get_user_by_email(db: Session, email: str) -> User | None:
    normalized_email = email.strip().lower()

    if not normalized_email:
        raise ValueError("Email cannot be empty")

    statement = select(User).where(
        User.email == normalized_email
    )

    return db.scalar(statement)


def get_user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    statement = select(User).where(
        User.id == user_id
    )

    return db.scalar(statement)


def create_user(
    db: Session,
    *,
    email: str,
    full_name: str,
) -> User:
    normalized_email = email.strip().lower()
    normalized_full_name = full_name.strip()

    if not normalized_email:
        raise ValueError("Email cannot be empty")

    if not normalized_full_name:
        raise ValueError("Full name cannot be empty")

    user = User(
        email=normalized_email,
        full_name=normalized_full_name,
    )

    db.add(user)
    db.flush()

    return user


def update_user(
    db: Session,
    user: User,
    updates: dict[str, Any],
) -> User:
    allowed_fields = {
        "full_name",
        "is_active",
    }

    unsupported_fields = set(updates) - allowed_fields

    if unsupported_fields:
        raise ValueError(
            f"Unsupported user fields: {sorted(unsupported_fields)}"
        )

    if updates.get("full_name") is not None:
        normalized_full_name = updates["full_name"].strip()

        if not normalized_full_name:
            raise ValueError("Full name cannot be empty")

        user.full_name = normalized_full_name

    if updates.get("is_active") is not None:
        active_status = updates["is_active"]

        if not isinstance(active_status, bool):
            raise ValueError("is_active must be a boolean")

        user.is_active = active_status

    db.flush()

    return user
