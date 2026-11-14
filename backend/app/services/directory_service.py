import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_directory(
    db: Session,
    *,
    organization_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> list[dict]:
    """Active colleagues of the caller, with name and role only.

    The database function returns rows only to owners, admins and members of
    the organization, so a viewer or an outsider gets an empty list even if
    the route check were missing.
    """
    rows = db.execute(
        text("""
            SELECT user_id, full_name, role
            FROM app_private.organization_directory(:organization_id)
            LIMIT :limit OFFSET :skip
        """),
        {"organization_id": organization_id, "limit": limit, "skip": skip},
    )

    return [dict(row._mapping) for row in rows]
