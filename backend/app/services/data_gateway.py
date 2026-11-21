"""The data gateway (AL-4): the only process that queries customer databases.

The API cannot open connection credentials (ADR-007), so the agent's data
tool asks this internal service instead. It holds what the worker holds
(WORKER_DATABASE_URL and the master private key), works as the eka_worker
role scoped to one organization, and answers two calls from the API:

- POST /v1/connections: the active PostgreSQL connections a person with
  this role may use (the connection's scope.roles), with their catalog;
- POST /v1/query: one read-only SELECT on one of those connections, with
  the agent's limits (DATA_QUERY_MAX_ROWS rows, DATA_QUERY_TIMEOUT_MS).

Nothing is stored and nothing of the query or the rows is logged. Every
call needs DATA_GATEWAY_TOKEN; without it the gateway refuses everything.
It must never be published outside the platform's private network.

    python -m scripts.run_data_gateway
"""

import datetime as dt
import decimal
import hmac
import logging
import uuid
from functools import lru_cache
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.connectors import postgresql
from app.connectors.base import ConnectorError
from app.core.config import settings
from app.core.errors import DomainError
from app.db.context import set_worker_context
from app.models.data_connection import DataConnection
from app.services.credential_service import load_credentials


logger = logging.getLogger("eka.data_gateway")

WORKER_ROLE = "eka_worker"
MAX_SQL_CHARS = 4000

Role = Literal["owner", "admin", "member", "viewer"]


class ConnectionsRequest(BaseModel):
    organization_id: uuid.UUID
    role: Role

    model_config = ConfigDict(extra="forbid")


class QueryRequest(ConnectionsRequest):
    connection_id: uuid.UUID
    sql: str = Field(min_length=1, max_length=MAX_SQL_CHARS)


def require_token(authorization: str | None = Header(default=None)) -> None:
    expected = settings.DATA_GATEWAY_TOKEN
    if not expected:
        raise HTTPException(503, "The data gateway is not configured")
    given = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(401, "Not allowed")


@lru_cache(maxsize=1)
def _engine():
    if not settings.WORKER_DATABASE_URL:
        raise HTTPException(503, "WORKER_DATABASE_URL is not set")
    return create_engine(settings.WORKER_DATABASE_URL, pool_pre_ping=True)


def get_session():
    db = Session(_engine())
    try:
        db.execute(text(f"SET LOCAL ROLE {WORKER_ROLE}"))
        yield db
    finally:
        db.rollback()
        db.close()


def usable(connection: DataConnection, role: str) -> bool:
    """Active PostgreSQL connections with a catalog that let this role in."""
    if connection.provider != "postgresql" or connection.status != "active":
        return False
    if connection.disconnected_at is not None or not connection.catalog:
        return False
    roles = ((connection.settings or {}).get("scope") or {}).get("roles")
    return not roles or role in roles


def _connections(db: Session, organization_id: uuid.UUID) -> list[DataConnection]:
    set_worker_context(db, organization_id=organization_id)
    return list(
        db.scalars(
            select(DataConnection)
            .where(DataConnection.organization_id == organization_id)
            .order_by(DataConnection.name)
        )
    )


def json_value(value):
    """A value the API can read back as JSON, without losing its meaning."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (dt.date, dt.datetime, dt.time, uuid.UUID)):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    return str(value)


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.post("/v1/connections", dependencies=[Depends(require_token)])
def connections(body: ConnectionsRequest, db: Session = Depends(get_session)):
    return {
        "connections": [
            {"connection_id": str(c.id), "name": c.name, "catalog": c.catalog}
            for c in _connections(db, body.organization_id)
            if usable(c, body.role)
        ]
    }


@app.post("/v1/query", dependencies=[Depends(require_token)])
def query(body: QueryRequest, db: Session = Depends(get_session)):
    connection = next(
        (
            c
            for c in _connections(db, body.organization_id)
            if c.id == body.connection_id and usable(c, body.role)
        ),
        None,
    )
    if connection is None:
        raise HTTPException(404, "No such connection for this person")
    try:
        credentials = load_credentials(
            db, organization_id=connection.organization_id, connection_id=connection.id
        )
        target = postgresql.build_target(dict(connection.settings), credentials)
        result = postgresql.run_read_only_query(
            target,
            body.sql,
            max_rows=settings.DATA_QUERY_MAX_ROWS,
            statement_timeout_ms=settings.DATA_QUERY_TIMEOUT_MS,
        )
    except postgresql.DatabaseQueryError as exc:
        # The customer database refused or failed the query: the agent
        # gives no answer. The query itself is never logged.
        raise HTTPException(422, str(exc)[:300]) from None
    except (ConnectorError, DomainError) as exc:
        logger.warning("data query on %s failed: %s", connection.id, type(exc).__name__)
        raise HTTPException(502, "The database could not be reached") from None
    return {
        "columns": list(result.columns),
        "rows": [[json_value(value) for value in row] for row in result.rows],
        "truncated": result.truncated,
    }
