import uuid

import pytest
from sqlalchemy import text

from app.db.context import (
    set_identity_context,
    set_organization_context,
)


pytestmark = pytest.mark.integration


def read_postgres_context(db):
    return db.execute(
        text(
            """
            SELECT
                current_setting('app.auth_issuer', true),
                current_setting('app.auth_subject', true),
                current_setting('app.user_id', true),
                current_setting('app.organization_id', true)
            """
        )
    ).one()


def test_postgres_context_starts_empty(postgres_db_session):
    context = read_postgres_context(postgres_db_session)

    assert context == ("", "", "", "")


def test_identity_and_organization_context_are_applied(
    postgres_db_session,
):
    user_id = uuid.uuid4()
    organization_id = uuid.uuid4()

    set_identity_context(
        postgres_db_session,
        issuer="https://identity.example.com/",
        subject="context-test-subject",
        user_id=user_id,
    )

    set_organization_context(
        postgres_db_session,
        organization_id=organization_id,
    )

    context = read_postgres_context(postgres_db_session)

    assert context == (
        "https://identity.example.com/",
        "context-test-subject",
        str(user_id),
        str(organization_id),
    )


def test_context_is_reapplied_after_commit(postgres_db_session):
    user_id = uuid.uuid4()
    organization_id = uuid.uuid4()

    set_identity_context(
        postgres_db_session,
        issuer="https://identity.example.com/",
        subject="commit-test-subject",
        user_id=user_id,
    )

    set_organization_context(
        postgres_db_session,
        organization_id=organization_id,
    )

    postgres_db_session.commit()

    context = read_postgres_context(postgres_db_session)

    assert context == (
        "https://identity.example.com/",
        "commit-test-subject",
        str(user_id),
        str(organization_id),
    )


def test_context_is_reapplied_after_rollback(postgres_db_session):
    user_id = uuid.uuid4()
    organization_id = uuid.uuid4()

    set_identity_context(
        postgres_db_session,
        issuer="https://identity.example.com/",
        subject="rollback-test-subject",
        user_id=user_id,
    )

    set_organization_context(
        postgres_db_session,
        organization_id=organization_id,
    )

    postgres_db_session.rollback()

    context = read_postgres_context(postgres_db_session)

    assert context == (
        "https://identity.example.com/",
        "rollback-test-subject",
        str(user_id),
        str(organization_id),
    )


def test_organization_context_requires_identity(postgres_db_session):
    with pytest.raises(RuntimeError, match="Authenticated user context"):
        set_organization_context(
            postgres_db_session,
            organization_id=uuid.uuid4(),
        )


def test_organization_context_cannot_be_switched(
    postgres_db_session,
):
    set_identity_context(
        postgres_db_session,
        issuer="https://identity.example.com/",
        subject="switch-test-subject",
        user_id=uuid.uuid4(),
    )

    set_organization_context(
        postgres_db_session,
        organization_id=uuid.uuid4(),
    )

    with pytest.raises(RuntimeError, match="cannot be changed"):
        set_organization_context(
            postgres_db_session,
            organization_id=uuid.uuid4(),
        )
