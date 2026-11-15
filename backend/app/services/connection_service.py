"""Manage the data sources an organization connects (ADR-006).

Each provider belongs to one kind of source, which decides how its data is
answered: documents by retrieval with citations, tabular files and
databases by queries. The kind is derived from the provider, never sent by
the client, so the two cannot disagree.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, InvalidInputError, NotFoundError
from app.models.data_connection import DataConnection


PROVIDERS = {
    "google_drive": "documents",
    "file_upload": "documents",
    "spreadsheet_upload": "tabular",
    "postgresql": "database",
}


class UnknownProviderError(InvalidInputError):
    pass


class ConnectionNotFoundError(NotFoundError):
    pass


class ConnectionNameTakenError(ConflictError):
    pass


class ConnectionDisconnectedError(ConflictError):
    pass


def _validate_provider_settings(provider: str, settings: dict) -> None:
    if provider == "postgresql":
        from app.connectors.postgresql import validate_settings

        validate_settings(settings)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _name_taken(
    db: Session,
    *,
    organization_id: uuid.UUID,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    query = select(DataConnection.id).where(
        DataConnection.organization_id == organization_id,
        DataConnection.name == name,
        DataConnection.status != "disconnected",
    )
    if exclude_id is not None:
        query = query.where(DataConnection.id != exclude_id)
    return db.scalars(query).first() is not None


def _flush(db: Session) -> None:
    # The partial unique index is the final word if two requests race.
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        if "uq_data_connections_active_name" in str(exc.orig):
            raise ConnectionNameTakenError(
                "A connection with this name already exists"
            ) from None
        raise


def list_connections(
    db: Session,
    *,
    organization_id: uuid.UUID,
    include_disconnected: bool = False,
) -> list[DataConnection]:
    query = select(DataConnection).where(
        DataConnection.organization_id == organization_id
    )
    if not include_disconnected:
        query = query.where(DataConnection.status != "disconnected")
    return list(db.scalars(query.order_by(DataConnection.created_at)))


def get_connection(
    db: Session,
    *,
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> DataConnection:
    connection = db.scalars(
        select(DataConnection).where(
            DataConnection.id == connection_id,
            DataConnection.organization_id == organization_id,
        )
    ).one_or_none()

    if connection is None:
        raise ConnectionNotFoundError("Connection not found")

    return connection


def create_connection(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    provider: str,
    name: str,
    settings: dict,
) -> DataConnection:
    kind = PROVIDERS.get(provider)
    if kind is None:
        raise UnknownProviderError(
            f"Unknown provider {provider}; available: "
            + ", ".join(sorted(PROVIDERS))
        )

    if _name_taken(db, organization_id=organization_id, name=name):
        raise ConnectionNameTakenError(
            "A connection with this name already exists"
        )
    _validate_provider_settings(provider, settings)

    connection = DataConnection(
        organization_id=organization_id,
        kind=kind,
        provider=provider,
        name=name,
        settings=settings,
        created_by_user_id=actor_user_id,
    )
    db.add(connection)
    _flush(db)
    return connection


def update_connection(
    db: Session,
    *,
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    name: str | None = None,
    status: str | None = None,
    settings: dict | None = None,
) -> DataConnection:
    connection = get_connection(
        db, organization_id=organization_id, connection_id=connection_id
    )

    if connection.status == "disconnected":
        raise ConnectionDisconnectedError(
            "A disconnected connection cannot change"
        )

    if name is not None and name != connection.name:
        if _name_taken(
            db,
            organization_id=organization_id,
            name=name,
            exclude_id=connection.id,
        ):
            raise ConnectionNameTakenError(
                "A connection with this name already exists"
            )
        connection.name = name

    if status is not None:
        connection.status = status

    if settings is not None:
        _validate_provider_settings(connection.provider, settings)
        connection.settings = settings

    connection.updated_at = _now()
    _flush(db)
    return connection


def disconnect_connection(
    db: Session,
    *,
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> DataConnection:
    connection = get_connection(
        db, organization_id=organization_id, connection_id=connection_id
    )

    if connection.status == "disconnected":
        raise ConnectionDisconnectedError(
            "This connection is already disconnected"
        )

    now = _now()
    connection.status = "disconnected"
    connection.disconnected_at = now
    connection.updated_at = now
    _flush(db)
    return connection
