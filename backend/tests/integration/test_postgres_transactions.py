import pytest
from sqlalchemy import select

from app.models import User


pytestmark = pytest.mark.integration

TEST_EMAIL = "transaction-rollback-check@example.com"


def test_outer_rollback_reverts_data_after_session_commit(
    postgres_db_session,
):
    user = User(
        email=TEST_EMAIL,
        full_name="PostgreSQL Rollback Test",
        is_active=True,
    )

    postgres_db_session.add(user)
    postgres_db_session.commit()

    # A sessão terminou a sua transação interna.
    assert not postgres_db_session.in_transaction()

    # A ligação continua dentro da transação exterior da fixture.
    connection = postgres_db_session.connection()

    assert connection.in_transaction()
    assert connection.in_nested_transaction()

    # O registo continua visível dentro da transação exterior.
    persisted_in_transaction = postgres_db_session.execute(
        select(User).where(User.email == TEST_EMAIL)
    ).scalar_one_or_none()

    assert persisted_in_transaction is not None


def test_previous_test_data_was_not_persisted(postgres_engine):
    with postgres_engine.connect() as connection:
        remaining = connection.execute(
            select(User.id).where(User.email == TEST_EMAIL)
        ).all()

    assert remaining == []
