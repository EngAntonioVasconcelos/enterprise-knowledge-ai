import socket
import uuid

import pytest

from app.connectors import postgresql
from app.core.config import settings
from app.core.errors import InvalidInputError
from app.models.background_job import BackgroundJob
from app.models.data_connection import DataConnection
from app.services import catalog_service
from app.services.catalog_service import INTROSPECT_JOB
from app.services.worker import run_once
from tests.conftest import test_engine


SETTINGS = {"host": "db.example.com", "database": "warehouse"}
CREDENTIALS = {"username": "reader", "password": "very-secret-password"}


@pytest.fixture
def organization(client):
    unique = uuid.uuid4().hex[:8]
    return client.post(
        "/api/v1/organizations/",
        json={"name": f"Db Org {unique}", "slug": f"db-{unique}"},
    ).json()["id"]


def _create(client, organization, settings_):
    return client.post(
        f"/api/v1/organizations/{organization}/connections/",
        json={"provider": "postgresql", "name": "Warehouse", "settings": settings_},
    )


def _resolves_to(monkeypatch, address):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, type=0: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))],
    )


# Settings


@pytest.mark.parametrize(
    "settings_",
    [
        {},
        {"database": "warehouse"},
        {"host": "db.example.com"},
        {**SETTINGS, "port": 0},
        {**SETTINGS, "port": "5432"},
        {**SETTINGS, "sslmode": "prefer"},
        {**SETTINGS, "sslmode": "disable"},
        {**SETTINGS, "schemas": []},
        {**SETTINGS, "host": "db.example.com sslmode=disable"},
        {**SETTINGS, "dbname": "other"},
    ],
)
def test_bad_settings_are_refused(client, organization, settings_):
    assert _create(client, organization, settings_).status_code == 400


def test_good_settings_are_kept(client, organization):
    response = _create(
        client, organization, {**SETTINGS, "port": 6543, "schemas": ["sales", "public"]}
    )

    assert response.status_code == 201
    assert response.json()["kind"] == "database"


def test_plain_text_connections_are_for_development_only(client, organization, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS", True)

    assert _create(client, organization, {**SETTINGS, "sslmode": "disable"}).status_code == 201


def test_plain_text_is_allowed_for_the_named_internal_host_only(client, organization, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_CONNECTOR_ALLOWED_INTERNAL_HOSTS", ["demo-sales"])
    plain = {**SETTINGS, "sslmode": "disable"}

    assert _create(client, organization, {**plain, "host": "demo-sales"}).status_code == 201
    for host in ("demo-sales.evil", SETTINGS["host"]):
        with pytest.raises(InvalidInputError):
            postgresql.validate_settings({**plain, "host": host})
    assert postgresql.private_addresses_allowed("Demo-Sales")


def test_a_target_needs_credentials_and_hides_them():
    with pytest.raises(postgresql.DatabaseConnectorError):
        postgresql.build_target(SETTINGS, None)

    target = postgresql.build_target(SETTINGS, CREDENTIALS)
    assert "very-secret-password" not in repr(target)
    assert (target.port, target.sslmode, target.schemas) == (5432, "require", ("public",))


# Where a connection may go


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.5", "192.168.1.10", "169.254.169.254", "::1", "fd00::1"]
)
def test_private_and_local_addresses_are_refused(monkeypatch, address):
    _resolves_to(monkeypatch, address)
    target = postgresql.build_target(SETTINGS, CREDENTIALS)

    with pytest.raises(postgresql.UnsafeHostError):
        postgresql.checked_address(target)


def test_public_addresses_are_used_as_checked(monkeypatch):
    _resolves_to(monkeypatch, "8.8.8.8")
    target = postgresql.build_target(SETTINGS, CREDENTIALS)

    assert postgresql.checked_address(target) == "8.8.8.8"


def test_development_may_reach_private_addresses(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS", True)
    _resolves_to(monkeypatch, "127.0.0.1")
    target = postgresql.build_target(SETTINGS, CREDENTIALS)

    assert postgresql.checked_address(target) == "127.0.0.1"


def test_production_may_reach_only_the_named_internal_host(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_CONNECTOR_ALLOWED_INTERNAL_HOSTS", ["demo-sales"])
    _resolves_to(monkeypatch, "172.18.0.4")

    named = postgresql.build_target({**SETTINGS, "host": "demo-sales"}, CREDENTIALS)
    assert postgresql.checked_address(named) == "172.18.0.4"

    # Any other name that resolves to a private address is still refused.
    other = postgresql.build_target({**SETTINGS, "host": "metadata.internal"}, CREDENTIALS)
    with pytest.raises(postgresql.UnsafeHostError):
        postgresql.checked_address(other)


def test_the_platform_database_host_cannot_be_named_as_internal(monkeypatch):
    monkeypatch.setattr(
        settings, "DATABASE_URL", "postgresql+psycopg://runtime:pw@postgres:5432/eka"
    )
    monkeypatch.setattr(
        settings, "DATABASE_CONNECTOR_ALLOWED_INTERNAL_HOSTS", ["postgres", "demo-sales"]
    )
    _resolves_to(monkeypatch, "172.18.0.2")
    # Another database on the platform's server: not its own endpoint, but
    # its host is the platform's, so the private address stays refused.
    target = postgresql.build_target(
        {**SETTINGS, "host": "postgres", "database": "other"}, CREDENTIALS
    )

    assert not postgresql.private_addresses_allowed("postgres")
    with pytest.raises(postgresql.UnsafeHostError):
        postgresql.checked_address(target)


def test_the_platform_database_is_refused_even_in_development(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(
        settings, "WORKER_DATABASE_URL", "postgresql+psycopg://worker:pw@db.example.com:5432/warehouse"
    )
    _resolves_to(monkeypatch, "127.0.0.1")
    target = postgresql.build_target(SETTINGS, CREDENTIALS)

    with pytest.raises(postgresql.UnsafeHostError):
        postgresql.checked_address(target)


def test_queries_are_wrapped_as_one_sub_query():
    wrapped = postgresql._wrap("  SELECT 1 ;; ", 10)

    assert wrapped == "SELECT * FROM (\nSELECT 1\n) AS eka_query LIMIT 11"
    with pytest.raises(postgresql.DatabaseQueryError):
        postgresql._wrap(" ; ", 10)


# The catalog job


def test_a_sync_of_a_database_refreshes_its_catalog(
    client, db_session, organization, monkeypatch
):
    connection_id = _create(client, organization, SETTINGS).json()["id"]
    monkeypatch.setattr(catalog_service, "_credentials", lambda db, c: CREDENTIALS)
    seen = []

    def introspect(target):
        seen.append(target)
        return {"schemas": ["public"], "tables": [{"name": "orders"}], "truncated": False}

    monkeypatch.setattr(catalog_service.postgresql, "introspect", introspect)
    base = f"/api/v1/organizations/{organization}/connections/{connection_id}"

    job = client.post(f"{base}/sync")
    assert job.status_code == 202
    assert db_session.get(BackgroundJob, uuid.UUID(job.json()["job_id"])).kind == INTROSPECT_JOB
    assert run_once(test_engine, worker_id="test", assume_role=None)["succeeded"] == 1

    db_session.expire_all()
    catalog = client.get(f"{base}/catalog").json()
    assert catalog["catalog"]["tables"] == [{"name": "orders"}]
    assert catalog["catalog_updated_at"] is not None
    assert seen[0].username == "reader"


def test_an_unreachable_database_puts_the_connection_in_error(
    client, db_session, organization, monkeypatch
):
    connection_id = _create(client, organization, SETTINGS).json()["id"]
    monkeypatch.setattr(catalog_service, "_credentials", lambda db, c: None)

    catalog_service.introspect_connection(db_session, connection_id=uuid.UUID(connection_id))
    db_session.commit()

    connection = db_session.get(DataConnection, uuid.UUID(connection_id))
    assert connection.status == "error"
    assert "no database credentials" in connection.last_error
    assert connection.catalog is None
