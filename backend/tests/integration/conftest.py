from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


@pytest.fixture(scope="session")
def postgres_engine():
    env = dotenv_values(ENV_FILE)
    database_url = env.get("EKA_TEST_RUNTIME_DATABASE_URL")

    if not database_url:
        pytest.skip("PostgreSQL test database URL not configured.")

    url = make_url(database_url)

    engine = create_engine(
        url,
        pool_pre_ping=True,
    )

    try:
        with engine.connect() as connection:
            database = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()

            user = connection.execute(
                text("SELECT current_user")
            ).scalar_one()

            if database != "enterprise_knowledge_ai_test":
                pytest.fail(
                    "Integration tests must use "
                    "enterprise_knowledge_ai_test."
                )

            if user != "eka_test_runtime":
                pytest.fail(
                    "Integration tests must use eka_test_runtime."
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
