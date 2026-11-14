import pytest
from sqlalchemy import select, text

from app.db.context import set_authentication_context
from app.models import User


pytestmark = pytest.mark.integration

TEST_ISSUER = "https://test-identity.example.com/"
TEST_SUBJECT = "transaction-rollback-check"
TEST_EMAIL = "transaction-rollback-check@example.com"


def test_outer_rollback_reverts_data_after_session_commit(
    postgres_db_session,
):
    db = postgres_db_session

    set_authentication_context(db, issuer=TEST_ISSUER, subject=TEST_SUBJECT)
    db.execute(
        text("SELECT app_private.provision_user(:email, :full_name)"),
        {"email": TEST_EMAIL, "full_name": "PostgreSQL Rollback Test"},
    )
    db.commit()

    # The session finished its own transaction.
    assert not db.in_transaction()

    # The connection is still inside the fixture's outer transaction.
    connection = db.connection()

    assert connection.in_transaction()
    assert connection.in_nested_transaction()

    # The row is still visible inside the outer transaction.
    persisted_in_transaction = db.execute(
        select(User).where(User.email == TEST_EMAIL)
    ).scalar_one_or_none()

    assert persisted_in_transaction is not None


def test_previous_test_data_was_not_persisted(postgres_engine):
    with postgres_engine.connect() as connection:
        # Present the same identity: row-level security would show the
        # account to this connection if the previous test had persisted it.
        connection.execute(
            text("""
                SELECT
                    set_config('app.auth_issuer', :issuer, true),
                    set_config('app.auth_subject', :subject, true)
            """),
            {"issuer": TEST_ISSUER, "subject": TEST_SUBJECT},
        )

        remaining = connection.execute(
            select(User.id).where(User.email == TEST_EMAIL)
        ).all()

    assert remaining == []
