import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from scripts.prepare_test_database import TEST_ADMIN_URL


pytestmark = pytest.mark.integration

RECOVER = text("""
    SELECT app_private.recover_organization_owner(
        :organization_id, :membership_id, :actor_user_id, :reason
    )
""")

REASON = "Sole owner left the company; ticket OPS-1234"


@pytest.fixture
def operator(postgres_engine):
    # Recovery runs through an operator login that holds
    # eka_platform_recovery. The test administrator is a superuser, which
    # PostgreSQL treats as a member of every role. Everything is rolled back.
    engine = create_engine(TEST_ADMIN_URL)
    connection = engine.connect()
    transaction = connection.begin()

    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


def _user(connection, prefix):
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    connection.execute(
        text("""
            INSERT INTO users (id, email, full_name, is_active,
                               created_at, updated_at)
            VALUES (:id, :email, 'Recovery Test User', true, :now, :now)
        """),
        {"id": user_id, "email": f"{prefix}-{user_id.hex}@example.com",
         "now": now},
    )
    return user_id


def _membership(connection, organization_id, user_id, role):
    membership_id = uuid.uuid4()
    privileged = role in ("owner", "admin")
    connection.execute(
        text("""
            INSERT INTO organization_memberships (
                id, organization_id, user_id, role, is_active,
                has_held_privileged_role, has_held_owner_role,
                created_at, updated_at
            )
            VALUES (:id, :org, :user, :role, true, :privileged, :owner,
                    now(), now())
        """),
        {"id": membership_id, "org": organization_id, "user": user_id,
         "role": role, "privileged": privileged, "owner": role == "owner"},
    )
    return membership_id


@pytest.fixture
def scenario(operator):
    # One organization whose only owner has left, a member who will take
    # over, an outsider and an active platform admin.
    absent_owner = _user(operator, "absent-owner")
    member = _user(operator, "next-owner")
    outsider = _user(operator, "outsider")
    admin = _user(operator, "platform-admin")

    organization_id = uuid.uuid4()
    operator.execute(
        text("""
            INSERT INTO organizations (id, name, slug, created_at,
                                       updated_at, created_by_user_id)
            VALUES (:id, 'Recovery Org', :slug, now(), now(), :creator)
        """),
        {"id": organization_id, "slug": f"recovery-{organization_id.hex}",
         "creator": absent_owner},
    )
    owner_membership = _membership(
        operator, organization_id, absent_owner, "owner"
    )
    member_membership = _membership(
        operator, organization_id, member, "member"
    )
    operator.execute(
        text("""
            INSERT INTO platform_memberships (id, user_id, role, is_active)
            VALUES (:id, :user, 'platform_admin', true)
        """),
        {"id": uuid.uuid4(), "user": admin},
    )

    return {
        "organization_id": organization_id,
        "owner_membership": owner_membership,
        "member_membership": member_membership,
        "member": member,
        "outsider": outsider,
        "admin": admin,
    }


def _recover(connection, s, **overrides):
    params = {
        "organization_id": s["organization_id"],
        "membership_id": s["member_membership"],
        "actor_user_id": s["admin"],
        "reason": REASON,
    }
    params.update(overrides)

    with connection.begin_nested():
        return connection.execute(RECOVER, params).scalar_one()


def test_recovery_promotes_member_and_deactivates_absent_owner(
    operator, scenario,
):
    event_id = _recover(operator, scenario)

    rows = operator.execute(
        text("""
            SELECT id, role, is_active, has_held_owner_role
            FROM organization_memberships
            WHERE organization_id = :org
        """),
        {"org": scenario["organization_id"]},
    ).all()
    state = {row.id: row for row in rows}

    new_owner = state[scenario["member_membership"]]
    assert (new_owner.role, new_owner.is_active) == ("owner", True)
    assert new_owner.has_held_owner_role is True

    absent = state[scenario["owner_membership"]]
    assert absent.is_active is False

    event = operator.execute(
        text("""
            SELECT recovered_user_id, actor_user_id, reason, database_login
            FROM organization_owner_recovery_events
            WHERE id = :id
        """),
        {"id": event_id},
    ).one()
    assert event.recovered_user_id == scenario["member"]
    assert event.actor_user_id == scenario["admin"]
    assert event.reason == REASON
    assert event.database_login == operator.execute(
        text("SELECT session_user")
    ).scalar_one()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"reason": "  short  "}, "reason of at least 10 characters"),
        ({"reason": None}, "reason of at least 10 characters"),
        ({"actor_user_id": "outsider"}, "active platform admin"),
        ({"organization_id": "random"}, "organization not found"),
        ({"membership_id": "random"}, "active member of the organization"),
        ({"membership_id": "owner_membership"}, "already an owner"),
    ],
)
def test_recovery_rejects_invalid_requests(
    operator, scenario, overrides, message,
):
    resolved = {
        key: (
            uuid.uuid4() if value == "random"
            else scenario[value] if isinstance(value, str) and value in scenario
            else value
        )
        for key, value in overrides.items()
    }

    with pytest.raises(DBAPIError, match=message):
        _recover(operator, scenario, **resolved)

    still_owner = operator.execute(
        text("""
            SELECT is_active FROM organization_memberships WHERE id = :id
        """),
        {"id": scenario["owner_membership"]},
    ).scalar_one()
    assert still_owner is True


def test_recovery_is_refused_to_the_application_role(postgres_db_session):
    with pytest.raises(DBAPIError, match="permission denied"):
        with postgres_db_session.begin_nested():
            postgres_db_session.execute(
                RECOVER,
                {
                    "organization_id": uuid.uuid4(),
                    "membership_id": uuid.uuid4(),
                    "actor_user_id": uuid.uuid4(),
                    "reason": REASON,
                },
            )


def test_recovery_is_refused_without_the_recovery_role(operator, scenario):
    operator.execute(
        text("CREATE ROLE eka_test_no_recovery NOLOGIN NOINHERIT")
    )
    operator.execute(
        text("""
            GRANT USAGE ON SCHEMA app_private TO eka_test_no_recovery;
            GRANT EXECUTE ON FUNCTION
                app_private.recover_organization_owner(uuid, uuid, uuid, text)
                TO eka_test_no_recovery;
            SET LOCAL SESSION AUTHORIZATION eka_test_no_recovery;
        """)
    )

    with pytest.raises(DBAPIError, match="platform recovery role"):
        _recover(operator, scenario)
