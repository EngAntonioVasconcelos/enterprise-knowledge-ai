
import uuid

import pytest

from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.user import User
from app.services.organization_service import create_organization


def create_test_user(db_session, is_active=True):
    user = User(
        email=f"{uuid.uuid4().hex}@example.com",
        full_name="Organization Creator",
        is_active=is_active,
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_create_organization_assigns_creator_as_owner(db_session):
    creator = create_test_user(db_session)

    organization = create_organization(
        db_session,
        name="Acme Corporation",
        slug="acme-corporation",
        creator_user_id=creator.id,
    )

    membership = db_session.query(OrganizationMembership).filter_by(
        organization_id=organization.id,
        user_id=creator.id,
    ).one()

    assert organization.id is not None
    assert organization.name == "Acme Corporation"
    assert organization.slug == "acme-corporation"
    assert organization.created_by_user_id == creator.id
    assert organization.creator.id == creator.id
    assert membership.role == "owner"
    assert membership.is_active is True


def test_create_organization_rejects_duplicate_slug(db_session):
    creator = create_test_user(db_session)

    create_organization(
        db_session,
        name="First Organization",
        slug="acme-corporation",
        creator_user_id=creator.id,
    )

    with pytest.raises(
        ValueError,
        match="Organization slug already exists",
    ):
        create_organization(
            db_session,
            name="Second Organization",
            slug="acme-corporation",
            creator_user_id=creator.id,
        )


def test_create_organization_rejects_nonexistent_creator(db_session):
    with pytest.raises(ValueError, match="User not found"):
        create_organization(
            db_session,
            name="Acme Corporation",
            slug="acme-corporation",
            creator_user_id=uuid.uuid4(),
        )

    assert db_session.query(Organization).count() == 0


def test_create_organization_rejects_inactive_creator(db_session):
    creator = create_test_user(db_session, is_active=False)

    with pytest.raises(ValueError, match="inactive user"):
        create_organization(
            db_session,
            name="Acme Corporation",
            slug="acme-corporation",
            creator_user_id=creator.id,
        )

    assert db_session.query(Organization).count() == 0
    assert db_session.query(OrganizationMembership).count() == 0


def test_create_organization_rejects_empty_name(db_session):
    creator = create_test_user(db_session)

    with pytest.raises(ValueError, match="name cannot be empty"):
        create_organization(
            db_session,
            name="   ",
            slug="valid-slug",
            creator_user_id=creator.id,
        )

    assert db_session.query(Organization).count() == 0


def test_create_organization_rejects_empty_slug(db_session):
    creator = create_test_user(db_session)

    with pytest.raises(ValueError, match="slug cannot be empty"):
        create_organization(
            db_session,
            name="Valid Organization",
            slug="   ",
            creator_user_id=creator.id,
        )

    assert db_session.query(Organization).count() == 0


def test_create_organization_normalizes_name_and_slug(db_session):
    creator = create_test_user(db_session)

    organization = create_organization(
        db_session,
        name="  Acme Corporation  ",
        slug="  ACME-CORPORATION  ",
        creator_user_id=creator.id,
    )

    assert organization.name == "Acme Corporation"
    assert organization.slug == "acme-corporation"


def test_create_organization_can_be_rolled_back_if_owner_creation_fails(
    db_session,
    monkeypatch,
):
    import app.services.organization_service as organization_service

    creator = create_test_user(db_session)

    def fail_owner_creation(*args, **kwargs):
        raise RuntimeError("Simulated owner creation failure")

    monkeypatch.setattr(
        organization_service,
        "create_initial_owner_membership",
        fail_owner_creation,
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated owner creation failure",
    ):
        organization_service.create_organization(
            db_session,
            name="Acme Corporation",
            slug="acme-rollback",
            creator_user_id=creator.id,
        )

    db_session.rollback()

    assert db_session.query(Organization).filter_by(
        slug="acme-rollback"
    ).count() == 0

    assert db_session.query(OrganizationMembership).count() == 0
