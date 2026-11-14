import os

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import sessionmaker

from scripts.prepare_test_database import (
    BACKEND_DIR,
    TEST_ADMIN_URL,
    TEST_DATABASE,
    TEST_RUNTIME_ROLE,
    TEST_RUNTIME_URL,
)


PREPARE_HINT = (
    "From the backend folder, start it with "
    "'docker compose -f ../infrastructure/test-db/docker-compose.yml "
    "up -d --wait' and then run 'python scripts/prepare_test_database.py'."
)


def _unavailable(reason: str) -> None:
    message = f"Integration test database unavailable: {reason} {PREPARE_HINT}"

    # Locally the tests are skipped; in CI a missing database is a failure,
    # so security tests can never be skipped silently.
    if os.environ.get("CI"):
        pytest.fail(message)

    pytest.skip(message)


def _expected_schema_version() -> str | None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))

    return ScriptDirectory.from_config(config).get_current_head()


def _applied_schema_version() -> str | None:
    admin_engine = create_engine(TEST_ADMIN_URL)

    try:
        with admin_engine.connect() as connection:
            return connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
    except (OperationalError, ProgrammingError):
        return None
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session")
def postgres_engine():
    engine = create_engine(
        TEST_RUNTIME_URL,
        pool_pre_ping=True,
    )

    try:
        try:
            with engine.connect() as connection:
                database, role, is_superuser, bypasses_rls = connection.execute(
                    text("""
                        SELECT
                            current_database(),
                            current_user,
                            r.rolsuper,
                            r.rolbypassrls
                        FROM pg_catalog.pg_roles AS r
                        WHERE r.rolname = current_user
                    """)
                ).one()
        except OperationalError:
            _unavailable("cannot connect as the runtime role.")

        if database != TEST_DATABASE:
            pytest.fail(f"Integration tests must use {TEST_DATABASE}.")

        if role != TEST_RUNTIME_ROLE:
            pytest.fail(f"Integration tests must use {TEST_RUNTIME_ROLE}.")

        if is_superuser or bypasses_rls:
            pytest.fail(
                "Integration tests must not run as a superuser "
                "or with BYPASSRLS: row-level security would not apply."
            )

        applied = _applied_schema_version()
        expected = _expected_schema_version()

        if applied != expected:
            pytest.fail(
                f"Test database schema is at {applied}, "
                f"but the code expects {expected}. {PREPARE_HINT}"
            )

        yield engine

    finally:
        engine.dispose()


@pytest.fixture
def postgres_db_session(postgres_engine):
    connection = postgres_engine.connect()
    outer_transaction = connection.begin()

    TestingSessionLocal = sessionmaker(
        bind=connection,
        autoflush=False,
        autocommit=False,
        join_transaction_mode="create_savepoint",
    )

    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()

        if outer_transaction.is_active:
            outer_transaction.rollback()

        connection.close()
