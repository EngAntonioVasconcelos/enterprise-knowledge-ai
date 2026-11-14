import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.db.context import set_organization_context, set_worker_context
from app.models import AuditEvent, DataConnection
from app.services.connection_service import (
    create_connection,
    disconnect_connection,
    update_connection,
)
from scripts.prepare_test_database import TEST_ADMIN_URL
from tests.integration.test_postgres_rls import (
    _authenticate,
    _create_organization,
    _create_user,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def connections_db(postgres_engine):
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
    owner = _create_user(db, "sources-owner")
    organization = _create_organization(db, owner)
    _authenticate(db, owner)
    set_organization_context(db, organization_id=organization.id)
    connection = create_connection(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        provider="google_drive",
        name="Company Drive",
        settings={"folder_ids": ["abc"]},
    )
    db.flush()
    return owner, organization, connection.id


def test_creating_and_changing_a_connection_is_audited(connections_db):
    db = connections_db
    _, organization, connection_id = _setup(db)

    update_connection(
        db,
        organization_id=organization.id,
        connection_id=connection_id,
        name="Drive",
        status="paused",
        settings={},
    )
    disconnect_connection(
        db, organization_id=organization.id, connection_id=connection_id
    )
    db.flush()
    db.expire_all()

    actions = db.scalars(
        select(AuditEvent.action)
        .where(AuditEvent.target_id == connection_id)
        .order_by(AuditEvent.id)
    ).all()
    assert actions == [
        "connection.created",
        "connection.renamed",
        "connection.status_changed",
        "connection.settings_changed",
        "connection.status_changed",
    ]

    connection = db.get(DataConnection, connection_id)
    assert connection.disconnected_at is not None


def test_the_application_cannot_forge_or_delete_connections(connections_db):
    db = connections_db
    owner, organization, connection_id = _setup(db)
    stranger = _create_user(db, "sources-stranger")
    other = _create_organization(db, stranger)
    _authenticate(db, owner)

    def connection(**overrides):
        now = datetime.now(timezone.utc)
        values = dict(
            id=uuid.uuid4(),
            organization_id=organization.id,
            kind="documents",
            provider="google_drive",
            name=f"Source {uuid.uuid4().hex[:6]}",
            settings={},
            created_by_user_id=owner.id,
            created_at=now,
            updated_at=now,
        )
        values.update(overrides)
        return insert(DataConnection).values(**values)

    rls = "row-level security"
    _refused(db, connection(organization_id=other.id), rls)
    _refused(db, connection(created_by_user_id=stranger.id), rls)
    _refused(db, connection(status="error"), rls)
    _refused(db, connection(provider="Not A Provider"), "ck_data_connections")
    _refused(
        db,
        connection(settings=[]),
        "ck_data_connections_settings",
    )

    row = DataConnection.id == connection_id
    _refused(
        db,
        update(DataConnection).where(row).values(provider="postgresql"),
        "permission denied",
    )
    _refused(
        db,
        text("DELETE FROM data_connections"),
        "permission denied",
    )


def test_disconnected_is_final_whatever_the_caller(connections_db):
    db = connections_db
    _, organization, connection_id = _setup(db)
    row = DataConnection.id == connection_id

    db.execute(
        update(DataConnection).where(row).values(status="disconnected")
    )
    db.expire_all()
    assert db.get(DataConnection, connection_id).disconnected_at is not None

    _refused(
        db,
        update(DataConnection).where(row).values(status="active"),
        "a disconnected connection cannot change",
    )


def test_other_organizations_do_not_see_the_connection(connections_db):
    db = connections_db
    _, _, connection_id = _setup(db)
    stranger = _create_user(db, "sources-stranger")
    _authenticate(db, stranger)

    db.expire_all()
    assert db.scalars(
        select(DataConnection.id).where(DataConnection.id == connection_id)
    ).all() == []


def test_the_worker_sees_only_the_organization_of_its_job(connections_db):
    db = connections_db
    _, organization, connection_id = _setup(db)
    organization_id = organization.id
    db.flush()
    # The worker cannot read organizations: keep the id, not the object.
    db.execute(text("SET ROLE eka_worker"))

    def visible():
        db.expire_all()
        return db.scalars(
            select(DataConnection.id).where(DataConnection.id == connection_id)
        ).all()

    db.info.clear()
    set_worker_context(db, organization_id=uuid.uuid4())
    assert visible() == []

    db.info.clear()
    set_worker_context(db, organization_id=organization_id)
    assert visible() == [connection_id]

    row = DataConnection.id == connection_id
    db.execute(
        update(DataConnection)
        .where(row)
        .values(status="error", last_error="Drive refused the token")
    )
    _refused(
        db,
        update(DataConnection).where(row).values(name="Renamed"),
        "permission denied",
    )
