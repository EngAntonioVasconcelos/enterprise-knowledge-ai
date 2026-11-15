"""The contract every source connector implements (ADR-006).

A connector only talks to its source: it lists what changed and fetches
text. Everything else (versions, permissions, storage, retries, audit) is
done once, by the sync engine (app/services/sync_service.py), the same way
for every source.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.services.document_permission_service import SourcePermission


class ConnectorError(Exception):
    """The source failed; the sync is retried later."""


class ConnectorAuthError(ConnectorError):
    """The source refused the credentials: retrying will not help until an
    admin fixes the connection."""


@dataclass(frozen=True)
class SourceItem:
    external_id: str
    title: str
    mime_type: str | None = None
    revision: str | None = None
    modified_at: datetime | None = None
    permissions: tuple[SourcePermission, ...] = ()


@dataclass(frozen=True)
class ChangeSet:
    changed: tuple[SourceItem, ...] = ()
    removed: tuple[str, ...] = ()
    # Opaque position to continue from next time (a change token).
    cursor: str | None = None
    # True when "changed" lists every item the source has: anything the
    # platform holds that is not listed was removed at the source.
    complete: bool = False
    extra: dict = field(default_factory=dict)


class SourceConnector(Protocol):
    def list_changes(self, cursor: str | None) -> ChangeSet: ...

    def fetch_text(self, item: SourceItem) -> str: ...


@dataclass(frozen=True)
class ConnectionContext:
    organization_id: uuid.UUID
    connection_id: uuid.UUID
    provider: str
    settings: dict
    credentials: dict | None


ConnectorFactory = Callable[[ConnectionContext], SourceConnector]

# provider -> factory. Each connector module registers itself here.
CONNECTORS: dict[str, ConnectorFactory] = {}


def register_connector(provider: str) -> Callable[[ConnectorFactory], ConnectorFactory]:
    def register(factory: ConnectorFactory) -> ConnectorFactory:
        if provider in CONNECTORS:
            raise ValueError(f"A connector for {provider} already exists")
        CONNECTORS[provider] = factory
        return factory

    return register
