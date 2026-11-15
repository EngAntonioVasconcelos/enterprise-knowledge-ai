"""Store and open connection credentials (ADR-007).

The API side (store_credentials, credentials_status) only ever holds public
keys, so it can seal a secret but never open one. Opening
(load_credentials) needs the master private key, which only the worker is
configured with.

The API reads and writes these tables with explicit columns: its database
role is not allowed to read the sealed bytes, so a full-row ORM load would
be refused.
"""

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import credential_crypto as crypto
from app.core.config import settings
from app.core.errors import DomainError, NotFoundError
from app.models.credential import ConnectionCredential, OrganizationKey
from app.services.connection_service import (
    ConnectionDisconnectedError,
    get_connection,
)


class CredentialStorageUnavailableError(DomainError):
    status_code = 503


class CredentialsNotFoundError(NotFoundError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _configured_key(value: str | None, name: str) -> bytes:
    if not value:
        raise CredentialStorageUnavailableError(
            f"Credential storage is not configured ({name} is not set)"
        )
    try:
        return crypto.decode_key(value)
    except ValueError:
        raise CredentialStorageUnavailableError(
            f"Credential storage is misconfigured ({name} is not a key)"
        ) from None


def master_public_key() -> bytes:
    return _configured_key(
        settings.CREDENTIALS_MASTER_PUBLIC_KEY,
        "CREDENTIALS_MASTER_PUBLIC_KEY",
    )


def master_private_key() -> bytes:
    """Worker only: the API process must not use this."""
    return _configured_key(
        settings.CREDENTIALS_MASTER_PRIVATE_KEY,
        "CREDENTIALS_MASTER_PRIVATE_KEY",
    )


def _organization_public_key(
    db: Session,
    organization_id: uuid.UUID,
) -> bytes:
    """The organization's public key, created on first use."""

    def existing() -> bytes | None:
        return db.execute(
            select(OrganizationKey.public_key).where(
                OrganizationKey.organization_id == organization_id
            )
        ).scalar_one_or_none()

    public = existing()
    if public is not None:
        return public

    master = master_public_key()
    public, private = crypto.generate_key_pair()
    sealed_private = crypto.seal(
        master,
        private,
        context=crypto.organization_key_context(organization_id),
    )
    # The private half exists in clear only in this function's memory.
    del private

    try:
        with db.begin_nested():
            db.execute(
                insert(OrganizationKey).values(
                    organization_id=organization_id,
                    public_key=public,
                    sealed_private_key=sealed_private,
                    master_key_fingerprint=crypto.fingerprint(master),
                    created_at=_now(),
                )
            )
    except IntegrityError:
        # Another request created it first: use that one.
        public = existing()
        if public is None:
            raise

    return public


def store_credentials(
    db: Session,
    *,
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    secret: dict,
) -> str:
    """Seal and save a connection's secret; return the key fingerprint."""
    connection = get_connection(
        db, organization_id=organization_id, connection_id=connection_id
    )
    if connection.status == "disconnected":
        raise ConnectionDisconnectedError(
            "A disconnected connection cannot receive credentials"
        )

    public = _organization_public_key(db, organization_id)
    key_fingerprint = crypto.fingerprint(public)
    sealed = crypto.seal(
        public,
        json.dumps(secret, separators=(",", ":")).encode("utf-8"),
        context=crypto.credential_context(organization_id, connection_id),
    )
    now = _now()

    exists = db.execute(
        select(ConnectionCredential.connection_id).where(
            ConnectionCredential.connection_id == connection_id
        )
    ).first()

    if exists:
        db.execute(
            update(ConnectionCredential)
            .where(ConnectionCredential.connection_id == connection_id)
            .values(
                sealed=sealed,
                organization_key_fingerprint=key_fingerprint,
                updated_at=now,
            )
        )
    else:
        db.execute(
            insert(ConnectionCredential).values(
                connection_id=connection_id,
                organization_id=organization_id,
                sealed=sealed,
                organization_key_fingerprint=key_fingerprint,
                created_at=now,
                updated_at=now,
            )
        )

    return key_fingerprint


def credentials_status(
    db: Session,
    *,
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> dict:
    get_connection(
        db, organization_id=organization_id, connection_id=connection_id
    )
    row = db.execute(
        select(
            ConnectionCredential.organization_key_fingerprint,
            ConnectionCredential.updated_at,
        ).where(ConnectionCredential.connection_id == connection_id)
    ).first()

    if row is None:
        return {"configured": False, "updated_at": None, "key": None}

    return {"configured": True, "updated_at": row[1], "key": row[0]}


def load_credentials(
    db: Session,
    *,
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    master_private: bytes | None = None,
) -> dict:
    """Worker only: open a connection's secret."""
    master_private = master_private or master_private_key()

    organization_key = db.execute(
        select(
            OrganizationKey.sealed_private_key,
            OrganizationKey.master_key_fingerprint,
        ).where(OrganizationKey.organization_id == organization_id)
    ).first()
    credential = db.execute(
        select(ConnectionCredential.sealed).where(
            ConnectionCredential.connection_id == connection_id,
            ConnectionCredential.organization_id == organization_id,
        )
    ).scalar_one_or_none()

    if organization_key is None or credential is None:
        raise CredentialsNotFoundError("This connection has no credentials")

    sealed_private, master_fingerprint = organization_key
    if master_fingerprint != crypto.fingerprint(
        crypto.public_key_of(master_private)
    ):
        raise crypto.CredentialCryptoError(
            "The organization key was sealed with another master key"
        )

    organization_private = crypto.open_sealed(
        master_private,
        sealed_private,
        context=crypto.organization_key_context(organization_id),
    )
    plaintext = crypto.open_sealed(
        organization_private,
        credential,
        context=crypto.credential_context(organization_id, connection_id),
    )
    return json.loads(plaintext)
