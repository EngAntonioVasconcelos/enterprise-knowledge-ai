import pytest
from sqlalchemy import text

from app.services.directory_service import list_directory
from app.services.membership_service import create_membership
from tests.integration.test_postgres_rls import (
    _authenticate,
    _create_organization,
    _create_user,
)


pytestmark = pytest.mark.integration


def _organization_with(db, roles):
    owner = _create_user(db, "directory-owner")
    organization = _create_organization(db, owner)
    _authenticate(db, owner)

    people = {"owner": owner}
    for role in roles:
        user = _create_user(db, f"directory-{role}")
        create_membership(
            db,
            organization_id=organization.id,
            actor_user_id=owner.id,
            user_id=user.id,
            role=role,
        )
        people[role] = user

    return organization, people


def test_members_see_names_and_roles_of_colleagues(postgres_db_session):
    db = postgres_db_session
    organization, people = _organization_with(db, ["member", "viewer"])

    _authenticate(db, people["member"])
    entries = list_directory(db, organization_id=organization.id)

    assert {entry["user_id"] for entry in entries} == {
        user.id for user in people.values()
    }
    assert all(set(entry) == {"user_id", "full_name", "role"} for entry in entries)


def test_viewers_and_outsiders_get_an_empty_directory(postgres_db_session):
    db = postgres_db_session
    organization, people = _organization_with(db, ["viewer"])
    outsider = _create_user(db, "directory-outsider")

    for user in (people["viewer"], outsider):
        _authenticate(db, user)
        assert list_directory(db, organization_id=organization.id) == []


def test_former_members_disappear_from_the_directory(postgres_db_session):
    db = postgres_db_session
    organization, people = _organization_with(db, ["member", "admin"])

    _authenticate(db, people["owner"])
    db.execute(
        text("""
            UPDATE organization_memberships SET is_active = false
            WHERE organization_id = :organization AND user_id = :user
        """),
        {"organization": organization.id, "user": people["admin"].id},
    )

    _authenticate(db, people["member"])
    listed = {
        entry["user_id"]
        for entry in list_directory(db, organization_id=organization.id)
    }

    assert people["admin"].id not in listed
    assert people["member"].id in listed


def test_members_still_cannot_read_colleagues_emails(postgres_db_session):
    db = postgres_db_session
    organization, people = _organization_with(db, ["member", "admin"])

    _authenticate(db, people["member"])
    emails = db.scalars(
        text("SELECT email FROM users WHERE id = :id"),
        {"id": people["admin"].id},
    ).all()

    assert emails == []
