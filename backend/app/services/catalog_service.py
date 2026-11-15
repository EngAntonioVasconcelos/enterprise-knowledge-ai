"""Describe a database connection's schema for the agent (the catalog).

Runs in the worker as the job ``connection.introspect`` (the worker is the
only side that can open the sealed credentials, ADR-007). Requesting a
sync of a database connection queues this job: for a database, "sync"
means refreshing what we know about its tables, never copying its data.

A failure to connect is not retried in a loop: the connection goes to
``error`` with the reason, and an admin fixes it and asks again.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.connectors import postgresql
from app.connectors.base import ConnectorError
from app.core.errors import DomainError
from app.models.background_job import BackgroundJob
from app.models.data_connection import DataConnection
from app.services.credential_service import load_credentials
from app.services.job_queue import job_handler


logger = logging.getLogger("eka.catalog")

INTROSPECT_JOB = "connection.introspect"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _credentials(db: Session, connection: DataConnection) -> dict | None:
    try:
        return load_credentials(
            db,
            organization_id=connection.organization_id,
            connection_id=connection.id,
        )
    except DomainError:
        return None


def introspect_connection(db: Session, *, connection_id: uuid.UUID) -> dict | None:
    connection = db.get(DataConnection, connection_id)
    if connection is None or connection.status not in ("active", "error"):
        return None
    if connection.provider != "postgresql":
        raise LookupError(f"No catalog for provider {connection.provider}")

    try:
        target = postgresql.build_target(
            dict(connection.settings), _credentials(db, connection)
        )
        catalog = postgresql.introspect(target)
    except (ConnectorError, DomainError) as exc:
        connection.status = "error"
        connection.last_error = f"Database unavailable: {exc}"[:500]
        db.flush()
        logger.warning("introspect %s failed: %s", connection.id, exc)
        return None

    connection.catalog = catalog
    connection.catalog_updated_at = _now()
    connection.status = "active"
    connection.last_error = None
    db.flush()
    logger.info("introspect %s: %d tables", connection.id, len(catalog["tables"]))
    return catalog


@job_handler(INTROSPECT_JOB)
def run_introspect_job(db: Session, job: BackgroundJob) -> None:
    introspect_connection(db, connection_id=uuid.UUID(job.payload["connection_id"]))
