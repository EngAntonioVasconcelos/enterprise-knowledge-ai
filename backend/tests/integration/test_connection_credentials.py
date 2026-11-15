import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.core import credential_crypto as crypto
from app.core.config import settings
from app.db.context import set_organization_context, set_worker_context
from app.models import AuditEvent, ConnectionCredential
from app.services.connection_service import (
    create_connection,
    disconnect_connection,
)
from app.services.credential_service import (
    CredentialsNotFoundError,
    load_credentials,
    store_credentials,
)
from scripts.prepare_test_database import TEST_ADMIN_URL
from tests.integration.test_postgres_rls import (
    _authenticate,
    _create_organization,
    _create_user,
)


pytestmark = pytest.mark.integration

SECRET = {"user": "reader", "password": "correct horse battery staple"}


@pytest.fixture
def master_key(monkeypatch):
    public, private = crypto.generate_key_pair()
    monkeypatch.setattr(
        settings, "CREDENTIALS_MASTER_PUBLIC_KEY", crypto.encode_key(public)
    )
    return private


@pytest.fixture
def secrets_db(postgres_engine):
    # One administrator connection that plays the API (SET ROLE eka_runtime)
    # and the worker (SET ROLE eka_worker) on the same uncommitted data.
    engine = create_engine(TEST_ADMIN_URL)
    connection = engine.connect()
    transaction = connection.begin()
    db = sessionmaker(
        bind=connection,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )()

    try:
        db.execute(text("SET ROLE eka_runtime"))
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def _refused(db, statement, fragment):
    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            db.execute(statement)
    assert fragment in str(error.value.orig)


def _setup(db):
    owner = _create_user(db, "secrets-owner")
    organization = _create_organization(db, owner)
    _authenticate(db, owner)
    set_organization_context(db, organization_id=organization.id)
    connection = create_connection(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        provider="postgresql",
        name="Warehouse",
        settings={},
    )
    db.flush()
    return owner, organization.id, connection.id


def _as_worker(db, organization_id):
    db.flush()
    db.execute(text("SET ROLE eka_worker"))
    db.info.clear()
    set_worker_context(db, organization_id=organization_id)
    db.expire_all()


def test_the_application_writes_a_secret_it_cannot_read(
    secrets_db, master_key
):
    db = secrets_db
    _, organization_id, connection_id = _setup(db)
    store_credentials(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
        secret=SECRET,
    )
    db.flush()

    assert db.execute(
        select(ConnectionCredential.connection_id)
    ).scalars().all() == [connection_id]

    _refused(
        db,
        text("SELECT sealed FROM connection_credentials"),
        "permission denied",
    )
    _refused(
        db,
        text("SELECT sealed_private_key FROM organization_keys"),
        "permission denied",
    )
    _refused(
        db,
        text("DELETE FROM connection_credentials"),
        "permission denied",
    )


def test_the_worker_opens_it_for_the_organization_of_its_job_only(
    secrets_db, master_key
):
    db = secrets_db
    _, organization_id, connection_id = _setup(db)
    store_credentials(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
        secret=SECRET,
    )

    _as_worker(db, uuid.uuid4())
    with pytest.raises(CredentialsNotFoundError):
        load_credentials(
            db,
            organization_id=organization_id,
            connection_id=connection_id,
            master_private=master_key,
        )

    db.info.clear()
    set_worker_context(db, organization_id=organization_id)
    assert load_credentials(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
        master_private=master_key,
    ) == SECRET

    _refused(db, text("SELECT id FROM users"), "permission denied")


def test_secrets_go_only_to_live_connections_of_the_organization(
    secrets_db, master_key
):
    db = secrets_db
    owner, organization_id, connection_id = _setup(db)
    stranger = _create_user(db, "secrets-stranger")
    other_organization = _create_organization(db, stranger)
    _authenticate(db, owner)

    def credential(**overrides):
        now = datetime.now(timezone.utc)
        values = dict(
            connection_id=connection_id,
            organization_id=organization_id,
            sealed=b"x" * 80,
            organization_key_fingerprint="x25519:test",
            created_at=now,
            updated_at=now,
        )
        values.update(overrides)
        return insert(ConnectionCredential).values(**values)

    rls = "row-level security"
    # A connection that does not exist, and an organization not managed.
    _refused(db, credential(connection_id=uuid.uuid4()), rls)
    _refused(db, credential(organization_id=other_organization.id), rls)

    disconnect_connection(
        db, organization_id=organization_id, connection_id=connection_id
    )
    db.flush()
    # A disconnected connection takes no secret.
    _refused(db, credential(), rls)


def test_disconnecting_destroys_the_secret_and_it_is_all_audited(
    secrets_db, master_key
):
    db = secrets_db
    _, organization_id, connection_id = _setup(db)

    for value in (SECRET, {"user": "reader", "password": "rotated"}):
        store_credentials(
            db,
            organization_id=organization_id,
            connection_id=connection_id,
            secret=value,
        )
    disconnect_connection(
        db, organization_id=organization_id, connection_id=connection_id
    )
    db.flush()
    db.expire_all()

    assert db.execute(
        select(ConnectionCredential.connection_id)
    ).scalars().all() == []

    actions = db.scalars(
        select(AuditEvent.action)
        .where(
            AuditEvent.target_id == connection_id,
            AuditEvent.action.like("connection.credentials%"),
        )
        .order_by(AuditEvent.id)
    ).all()
    assert actions == [
        "connection.credentials_set",
        "connection.credentials_replaced",
        "connection.credentials_destroyed",
    ]
