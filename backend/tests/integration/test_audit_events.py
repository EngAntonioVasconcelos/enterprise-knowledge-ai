import uuid

import pytest
from sqlalchemy import create_engine, delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import AuditEvent, Organization
from app.services.audit_service import list_audit_events
from app.services.invitation_service import (
    accept_invitation,
    create_invitation,
    revoke_invitation,
)
from app.services.membership_service import (
    create_membership,
    update_membership_role,
)
from scripts.prepare_test_database import TEST_ADMIN_URL
from tests.integration.test_postgres_rls import (
    _authenticate,
    _authenticate_as,
    _create_organization,
    _create_user,
)


pytestmark = pytest.mark.integration


def _actions(db, organization_id):
    return [
        event.action
        for event in reversed(
            list_audit_events(db, organization_id=organization_id)
        )
    ]


def test_membership_changes_are_recorded_with_their_actor(postgres_db_session):
    db = postgres_db_session
    owner = _create_user(db, "audit-owner")
    member = _create_user(db, "audit-member")
    organization = _create_organization(db, owner)

    _authenticate(db, owner)
    create_membership(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=member.id,
        role="member",
    )
    update_membership_role(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=member.id,
        role="admin",
    )

    events = list_audit_events(db, organization_id=organization.id)
    by_action = {event.action: event for event in events}

    assert _actions(db, organization.id) == [
        "organization.created",
        "membership.created",
        "membership.created",
        "membership.role_changed",
    ]
    change = by_action["membership.role_changed"]
    assert change.actor_user_id == owner.id
    assert change.actor_database_login == "eka_runtime"
    assert change.details == {
        "user_id": str(member.id),
        "from": "member",
        "to": "admin",
    }


def test_invitation_lifecycle_is_recorded(postgres_db_session):
    db = postgres_db_session
    owner = _create_user(db, "audit-inviter")
    guest = _create_user(db, "audit-guest")
    organization = _create_organization(db, owner)
    _authenticate(db, owner)

    revoked, _ = create_invitation(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        email=f"someone-{uuid.uuid4().hex}@example.com",
        role="member",
    )
    revoke_invitation(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        invitation_id=revoked.id,
    )
    _, token = create_invitation(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        email=guest.email,
        role="viewer",
    )

    _authenticate(db, guest)
    accept_invitation(db, token=token)

    _authenticate(db, owner)
    actions = _actions(db, organization.id)

    assert actions[-5:] == [
        "invitation.created",
        "invitation.revoked",
        "invitation.created",
        "membership.created",
        "invitation.accepted",
    ]


def test_status_changes_record_the_platform_login(postgres_engine):
    with Session(postgres_engine) as db:
        owner = _create_user(db, "audit-status")
        organization = _create_organization(db, owner)
        organization_id, owner_id = organization.id, owner.id
        db.commit()

    engine = create_engine(TEST_ADMIN_URL)
    try:
        with engine.begin() as connection:
            operator_login = connection.execute(
                text("SELECT session_user")
            ).scalar_one()
            connection.execute(
                update(Organization)
                .where(Organization.id == organization_id)
                .values(status="suspended")
            )
            connection.execute(
                update(Organization)
                .where(Organization.id == organization_id)
                .values(status="active")
            )
    finally:
        engine.dispose()

    with Session(postgres_engine) as db:
        _authenticate_as(db, owner_id)
        changes = [
            event
            for event in list_audit_events(db, organization_id=organization_id)
            if event.action == "organization.status_changed"
        ]

    assert [change.details for change in reversed(changes)] == [
        {"from": "active", "to": "suspended"},
        {"from": "suspended", "to": "active"},
    ]
    assert {change.actor_user_id for change in changes} == {None}
    assert {change.actor_database_login for change in changes} == {
        operator_login
    }


def test_only_owners_and_admins_read_the_log(postgres_db_session):
    db = postgres_db_session
    owner = _create_user(db, "audit-reader-owner")
    member = _create_user(db, "audit-reader-member")
    outsider = _create_user(db, "audit-reader-outsider")
    organization = _create_organization(db, owner)
    _authenticate(db, owner)
    create_membership(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=member.id,
        role="member",
    )

    assert list_audit_events(db, organization_id=organization.id)

    for user in (member, outsider):
        _authenticate(db, user)
        assert list_audit_events(db, organization_id=organization.id) == []


def test_the_application_cannot_write_change_or_erase_the_log(
    postgres_db_session,
):
    db = postgres_db_session
    owner = _create_user(db, "audit-forger")
    organization = _create_organization(db, owner)
    _authenticate(db, owner)
    newest = list_audit_events(db, organization_id=organization.id)[0]
    event_id, action = newest.id, newest.action

    attempts = (
        insert(AuditEvent).values(
            organization_id=organization.id,
            actor_database_login="forged",
            action="forged.event",
            target_type="organization",
            target_id=organization.id,
        ),
        update(AuditEvent)
        .where(AuditEvent.id == event_id)
        .values(action="rewritten"),
        delete(AuditEvent).where(AuditEvent.id == event_id),
    )

    for statement in attempts:
        with pytest.raises(DBAPIError, match="permission denied"):
            with db.begin_nested():
                db.execute(statement)

    assert db.scalar(
        select(AuditEvent.action).where(AuditEvent.id == event_id)
    ) == action
