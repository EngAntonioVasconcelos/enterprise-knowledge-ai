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
