import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text, update
from sqlalchemy.exc import DBAPIError

from app.models import Organization
from app.services.invitation_service import create_invitation
from app.services.membership_service import (
    create_membership,
    update_membership_role,
)
from scripts.prepare_test_database import TEST_ADMIN_URL
from tests.integration.test_postgres_rls import (
    _authenticate_as,
    _create_organization,
    _create_user,
)


pytestmark = pytest.mark.integration


def _set_status(organization_id, status):
    # Status changes are a platform operation: they run on the operator's
    # connection (the test administrator) and are committed, so the
    # application's session sees them.
    engine = create_engine(TEST_ADMIN_URL)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE organizations SET status = :s WHERE id = :id"),
                {"s": status, "id": organization_id},
            )
    finally:
        engine.dispose()


def test_new_organizations_are_active(postgres_db_session):
    db = postgres_db_session
    owner = _create_user(db, "status-owner")

    organization = _create_organization(db, owner)
    db.refresh(organization)

    assert organization.status == "active"


def test_a_person_creates_at_most_three_organizations(postgres_db_session):
    db = postgres_db_session
    owner = _create_user(db, "limit-owner")

    for _ in range(3):
        _create_organization(db, owner)

    with pytest.raises(DBAPIError, match="organization limit reached"):
        with db.begin_nested():
            _create_organization(db, owner)


def test_the_application_cannot_change_the_status(postgres_db_session):
    db = postgres_db_session
    owner = _create_user(db, "status-change")
    organization = _create_organization(db, owner)

    with pytest.raises(DBAPIError, match="only be changed by the platform"):
        with db.begin_nested():
            db.execute(
                update(Organization)
                .where(Organization.id == organization.id)
                .values(status="suspended")
            )


def test_a_suspended_organization_is_read_only(postgres_engine):
    from sqlalchemy.orm import Session

    with Session(postgres_engine) as db:
        owner = _create_user(db, "suspended-owner")
        member = _create_user(db, "suspended-member")
        organization = _create_organization(db, owner)
        create_membership(
            db,
            organization_id=organization.id,
            actor_user_id=owner.id,
            user_id=member.id,
            role="member",
        )
        organization_id, owner_id, member_id = (
            organization.id, owner.id, member.id,
        )
        db.commit()

    _set_status(organization_id, "suspended")

    try:
        with Session(postgres_engine) as db:
            _authenticate_as(db, owner_id)

            assert db.get(Organization, organization_id).status == "suspended"

            with pytest.raises(DBAPIError, match="organization is not active"):
                with db.begin_nested():
                    update_membership_role(
                        db,
                        organization_id=organization_id,
                        actor_user_id=owner_id,
                        user_id=member_id,
                        role="viewer",
                    )

            with pytest.raises(DBAPIError, match="organization is not active"):
                with db.begin_nested():
                    create_invitation(
                        db,
                        organization_id=organization_id,
                        actor_user_id=owner_id,
                        email=f"guest-{uuid.uuid4().hex}@example.com",
                        role="member",
                    )

            with pytest.raises(DBAPIError, match="organization is not active"):
                with db.begin_nested():
                    db.execute(
                        update(Organization)
                        .where(Organization.id == organization_id)
                        .values(name="Renamed While Suspended")
                    )
    finally:
        _set_status(organization_id, "active")


def test_deleted_organizations_do_not_count_towards_the_limit(postgres_engine):
    from sqlalchemy.orm import Session

    with Session(postgres_engine) as db:
        owner = _create_user(db, "limit-deleted")
        first = _create_organization(db, owner)
        _create_organization(db, owner)
        _create_organization(db, owner)
        first_id, owner_id = first.id, owner.id
        db.commit()

    _set_status(first_id, "deleted")

    with Session(postgres_engine) as db:
        fourth = _create_organization(db, SimpleNamespace(id=owner_id))
        assert fourth.id != first_id
        db.rollback()
