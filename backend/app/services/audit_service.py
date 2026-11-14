import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent


def list_audit_events(
    db: Session,
    *,
    organization_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> list[AuditEvent]:
    """Newest first. Row-level security limits this to owners and admins."""
    return list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.organization_id == organization_id)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .offset(skip)
            .limit(limit)
        )
    )
