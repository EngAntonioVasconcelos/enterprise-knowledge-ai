import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from scripts import bootstrap_service_logins
from scripts.prepare_test_database import TEST_ADMIN_URL


pytestmark = pytest.mark.integration

PASSWORD = "local-test-worker-login-only"


def test_the_worker_login_can_only_switch_to_the_worker(postgres_engine, monkeypatch):
    monkeypatch.setenv("EKA_ADMIN_DATABASE_URL", TEST_ADMIN_URL)
    monkeypatch.setenv("EKA_WORKER_PASSWORD", PASSWORD)
    monkeypatch.delenv("EKA_MAILER_PASSWORD", raising=False)
    assert bootstrap_service_logins.main() == 0
    # Running it again changes nothing and keeps working.
    assert bootstrap_service_logins.main() == 0

    admin = create_engine(TEST_ADMIN_URL)
    with admin.connect() as connection:
        login = connection.execute(
            text(
                "SELECT rolsuper, rolbypassrls, rolinherit, rolcanlogin "
                "FROM pg_catalog.pg_roles WHERE rolname = 'eka_worker_login'"
            )
        ).one()
        memberships = connection.execute(
            text(
                "SELECT r.rolname, m.inherit_option, m.set_option "
                "FROM pg_catalog.pg_auth_members AS m "
                "JOIN pg_catalog.pg_roles AS r ON r.oid = m.roleid "
                "JOIN pg_catalog.pg_roles AS u ON u.oid = m.member "
                "WHERE u.rolname = 'eka_worker_login'"
            )
        ).all()
    admin.dispose()
    assert tuple(login) == (False, False, False, True)
    assert [tuple(row) for row in memberships] == [("eka_worker", False, True)]

    url = make_url(TEST_ADMIN_URL).set(username="eka_worker_login", password=PASSWORD)
    worker = create_engine(url)
    try:
        with worker.connect() as connection:
            # Without switching role, nothing can be read.
            with pytest.raises(DBAPIError):
                connection.execute(text("SELECT count(*) FROM background_jobs")).one()
        with worker.connect() as connection:
            with pytest.raises(DBAPIError):
                connection.execute(text("SET ROLE eka_runtime"))
        with worker.connect() as connection:
            connection.execute(text("SET ROLE eka_worker"))
            connection.execute(text("SELECT count(*) FROM background_jobs")).one()
    finally:
        worker.dispose()


def test_a_missing_password_skips_a_new_login(postgres_engine, monkeypatch, capsys):
    monkeypatch.setenv("EKA_ADMIN_DATABASE_URL", TEST_ADMIN_URL)
    monkeypatch.delenv("EKA_MAILER_PASSWORD", raising=False)
    monkeypatch.delenv("EKA_WORKER_PASSWORD", raising=False)
    admin = create_engine(TEST_ADMIN_URL)
    with admin.connect() as connection:
        existed = connection.execute(
            text("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'eka_mailer_login'")
        ).first()
    admin.dispose()
    assert bootstrap_service_logins.main() == 0
    if not existed:
        assert "eka_mailer_login: skipped (EKA_MAILER_PASSWORD not set)" in capsys.readouterr().out
