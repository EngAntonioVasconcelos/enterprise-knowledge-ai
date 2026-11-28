import uuid
from types import SimpleNamespace

from app.core.config import settings
from scripts import create_demo_connection as demo


def _row(name, slug=None):
    return SimpleNamespace(id=uuid.uuid4(), name=name, slug=slug or name.lower(), user_id=uuid.uuid4())


def test_only_the_development_database_with_private_hosts(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS", True)
    assert demo.check_target("postgresql+psycopg://a:b@localhost:1996/eka_dev") is None
    assert "1996" in demo.check_target("postgresql+psycopg://a:b@db.example.com:5432/prod")
    assert "not set" in demo.check_target(None)
    monkeypatch.setattr(settings, "DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS", False)
    assert "PRIVATE_HOSTS" in demo.check_target("postgresql+psycopg://a:b@localhost:1996/eka_dev")


def test_the_organization_is_chosen_or_asked_for():
    acme = _row("Acme")
    one, problem = demo.choose([acme, acme], None)
    assert one is acme and problem is None

    other = _row("Beta", "beta-lda")
    none, problem = demo.choose([acme, other], None)
    assert none is None and "--organization" in problem
    assert demo.choose([acme, other], "beta-lda")[0] is other
    assert demo.choose([acme, other], "ACME")[0] is acme
    assert demo.choose([], None)[1] == "no active organization with an owner"


def test_the_demo_connection_is_valid_and_read_only_by_design():
    from app.connectors import postgresql

    settings_before = settings.DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS
    settings.DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS = True
    try:
        assert postgresql.validate_settings(dict(demo.DEMO_SETTINGS))
    finally:
        settings.DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS = settings_before
    assert demo.DEMO_SECRET["username"] == "eka_reader"


def test_production_needs_the_named_internal_host_and_the_password(monkeypatch):
    url = "postgresql+psycopg://a:b@postgres:5432/eka"
    monkeypatch.setattr(settings, "DATABASE_CONNECTOR_ALLOWED_INTERNAL_HOSTS", [])
    monkeypatch.setenv("DEMO_SALES_READER_PASSWORD", "generated-on-the-server")
    assert "demo-sales" in demo.check_target(url, production=True)

    monkeypatch.setattr(settings, "DATABASE_CONNECTOR_ALLOWED_INTERNAL_HOSTS", ["demo-sales"])
    assert demo.check_target(url, production=True) is None

    monkeypatch.delenv("DEMO_SALES_READER_PASSWORD")
    assert "DEMO_SALES_READER_PASSWORD" in demo.check_target(url, production=True)


def test_the_production_connection_uses_the_internal_host_and_the_server_password(monkeypatch):
    from app.connectors import postgresql

    monkeypatch.setattr(settings, "DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS", False)
    monkeypatch.setattr(settings, "DATABASE_CONNECTOR_ALLOWED_INTERNAL_HOSTS", ["demo-sales"])
    monkeypatch.setenv("DEMO_SALES_READER_PASSWORD", "generated-on-the-server")
    connection_settings, secret = demo.demo_connection(production=True)

    assert connection_settings["host"] == "demo-sales" and connection_settings["port"] == 5432
    assert postgresql.validate_settings(dict(connection_settings))
    assert secret == {"username": "eka_reader", "password": "generated-on-the-server"}
    # Development keeps its local, throwaway login.
    assert demo.demo_connection(production=False)[1] == demo.DEMO_SECRET
