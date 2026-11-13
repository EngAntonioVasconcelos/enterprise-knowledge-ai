import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db.context import (
    set_identity_context,
    set_organization_context,
)
from app.models import Organization, OrganizationMembership, User
from app.services.membership_service import create_membership
from app.services.organization_service import create_organization


pytestmark = pytest.mark.integration

TEST_ISSUER = "https://test-identity.example.com/"


def _create_user(db, prefix="rls-user"):
    unique = uuid.uuid4().hex

    user = User(
        email=f"{prefix}-{unique}@example.com",
        full_name="RLS Integration Test User",
        is_active=True,
    )

    db.add(user)
    db.flush()

    return user


def _authenticate(db, user):
    set_identity_context(
        db,
        issuer=TEST_ISSUER,
        subject=f"test-subject-{user.id}",
        user_id=user.id,
    )


def _create_organization(db, creator):
    _authenticate(db, creator)

    unique = uuid.uuid4().hex[:12]

    return create_organization(
        db,
        name=f"RLS Organization {unique}",
        slug=f"rls-org-{unique}",
        creator_user_id=creator.id,
    )


def _clear_database_context(db):
    db.execute(
        text("""
            SELECT
                set_config('app.auth_issuer', '', true),
                set_config('app.auth_subject', '', true),
                set_config('app.user_id', '', true),
                set_config('app.organization_id', '', true)
        """)
    )


def test_bootstrap_creates_organization_and_initial_owner(
    postgres_db_session,
):
    db = postgres_db_session

    creator = _create_user(db)

    organization = _create_organization(db, creator)

    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == creator.id,
        )
    )

    assert organization.created_by_user_id == creator.id
    assert membership is not None
    assert membership.role == "owner"
    assert membership.is_active is True
    assert membership.has_held_privileged_role is True


def test_user_without_identity_context_cannot_read_organizations(
    postgres_db_session,
):
    db = postgres_db_session

    creator = _create_user(db)
    organization = _create_organization(db, creator)

    _clear_database_context(db)

    result = db.scalar(
        select(Organization).where(
            Organization.id == organization.id
        )
    )

    assert result is None


def test_user_cannot_access_another_tenants_organization(
    postgres_db_session,
):
    db = postgres_db_session

    user_a = _create_user(db, "tenant-a")
    organization_a = _create_organization(db, user_a)

    user_b = _create_user(db, "tenant-b")
    organization_b = _create_organization(db, user_b)

    _authenticate(db, user_a)
    set_organization_context(
        db,
        organization_id=organization_a.id,
    )

    visible_organization = db.scalar(
        select(Organization).where(
            Organization.id == organization_b.id
        )
    )

    visible_memberships = db.scalars(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id
            == organization_b.id
        )
    ).all()

    assert visible_organization is None
    assert visible_memberships == []


def test_member_cannot_insert_membership_directly(
    postgres_db_session,
):
    db = postgres_db_session

    owner = _create_user(db, "owner")
    organization = _create_organization(db, owner)

    member = _create_user(db, "member")
    new_user = _create_user(db, "new-user")

    create_membership(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=member.id,
        role="member",
    )

    _authenticate(db, member)

    unauthorized_membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=new_user.id,
        role="member",
        is_active=True,
        has_held_privileged_role=False,
    )

    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.add(unauthorized_membership)
            db.flush()


def test_owner_can_create_membership_in_own_organization(
    postgres_db_session,
):
    db = postgres_db_session

    owner = _create_user(db, "owner")
    organization = _create_organization(db, owner)

    new_user = _create_user(db, "new-member")

    membership = create_membership(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=new_user.id,
        role="member",
    )

    assert membership.organization_id == organization.id
    assert membership.user_id == new_user.id
    assert membership.role == "member"
    assert membership.is_active is True

def test_inactive_membership_cannot_read_organization(postgres_db_session):
    db = postgres_db_session
    creator = _create_user(db, "inactive-owner")
    organization = _create_organization(db, creator)

    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == creator.id,
        )
    )
    assert membership is not None

    membership.is_active = False
    db.flush()

    result = db.scalar(
        select(Organization).where(Organization.id == organization.id)
    )
    assert result is None


def test_user_without_membership_cannot_read_tenant(postgres_db_session):
    db = postgres_db_session
    creator = _create_user(db, "tenant-owner")
    outsider = _create_user(db, "tenant-outsider")
    organization = _create_organization(db, creator)

    _authenticate(db, outsider)

    result = db.scalar(
        select(Organization).where(Organization.id == organization.id)
    )
    assert result is None


def test_owner_cannot_update_another_tenants_organization(postgres_db_session):
    db = postgres_db_session

    owner_a = _create_user(db, "owner-a")
    organization_a = _create_organization(db, owner_a)

    owner_b = _create_user(db, "owner-b")
    organization_b = _create_organization(db, owner_b)

    _authenticate(db, owner_a)
    set_organization_context(db, organization_id=organization_a.id)

    result = db.execute(
        Organization.__table__.update()
        .where(Organization.id == organization_b.id)
        .values(name="Unauthorized modification")
    )

    assert result.rowcount == 0

    visible_organization = db.scalar(
        select(Organization).where(Organization.id == organization_b.id)
    )
    assert visible_organization is None


def test_bootstrap_cannot_create_a_second_initial_owner(postgres_db_session):
    db = postgres_db_session
    creator = _create_user(db, "bootstrap-owner")
    organization = _create_organization(db, creator)

    from app.services.membership_service import create_initial_owner_membership

    with pytest.raises(ValueError):
        create_initial_owner_membership(
            db,
            organization_id=organization.id,
            user_id=creator.id,
        )


def test_transaction_local_context_is_cleared_after_commit(postgres_engine):
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                text("""
                    SELECT set_config(
                        'app.user_id',
                        '11111111-1111-1111-1111-111111111111',
                        true
                    )
                """)
            )

            current_user_id = connection.execute(
                text("SELECT current_setting('app.user_id', true)")
            ).scalar_one()
            assert current_user_id == "11111111-1111-1111-1111-111111111111"

            transaction.commit()

            with connection.begin():
                current_user_id_after_commit = connection.execute(
                    text("""
                        SELECT COALESCE(
                            current_setting('app.user_id', true),
                            ''
                        )
                    """)
                ).scalar_one()

            assert current_user_id_after_commit == ""

        except Exception:
            if transaction.is_active:
                transaction.rollback()
            raise


def test_model_a_documents_runtime_context_spoofing_limitation(postgres_db_session):
    db = postgres_db_session
    creator = _create_user(db, "spoof-target")
    organization = _create_organization(db, creator)

    # This deliberately simulates a runtime connection setting forged identity
    # context. Model A trusts the backend to establish these values correctly.
    db.execute(
        text("""
            SELECT
                set_config('app.auth_issuer', :issuer, true),
                set_config('app.auth_subject', :subject, true),
                set_config('app.user_id', :user_id, true),
                set_config('app.organization_id', '', true)
        """),
        {
            "issuer": TEST_ISSUER,
            "subject": f"forged-subject-{creator.id}",
            "user_id": str(creator.id),
        },
    )

    result = db.scalar(
        select(Organization).where(Organization.id == organization.id)
    )

    # Expected under Model A: the database trusts the context supplied
    # by the application role, so a forged context can impersonate a member.
    assert result is not None

from sqlalchemy import update


def _create_admin_context(db):
    owner = _create_user(db, "direct-sql-owner")
    organization = _create_organization(db, owner)

    admin = _create_user(db, "direct-sql-admin")

    _authenticate(db, owner)
    create_membership(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=admin.id,
        role="admin",
    )

    _authenticate(db, admin)
    set_organization_context(db, organization_id=organization.id)

    return owner, admin, organization


def test_db01_admin_cannot_insert_owner_directly(postgres_db_session):
    db = postgres_db_session
    _, admin, organization = _create_admin_context(db)
    target = _create_user(db, "direct-owner-target")

    try:
        with db.begin_nested():
            db.add(
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=target.id,
                    role="owner",
                    has_held_privileged_role=True,
                    has_held_owner_role=True,
                    is_active=True,
                )
            )
            db.flush()

        pytest.fail("A inserção foi permitida. DB-01 continua vulnerável.")

    except DBAPIError as exc:
        error = str(exc.orig)
        print("\nDB-01 ERROR:", error)

        assert "row-level security" in error.lower(), (
            f"A operação foi rejeitada, mas não pela RLS: {error}"
        )

@pytest.mark.xfail(
    strict=True,
    reason="DB-02: current INSERT RLS policy permits admins to create admins",
)
def test_db02_admin_cannot_insert_admin_directly(postgres_db_session):
    db = postgres_db_session
    _, admin, organization = _create_admin_context(db)
    target = _create_user(db, "direct-admin-target")

    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.add(
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=target.id,
                    role="admin",
                    has_held_privileged_role=True,
                    is_active=True,
                )
            )
            db.flush()


@pytest.mark.xfail(
    strict=True,
    reason="DB-03: current UPDATE policy does not prevent membership transfers",
)
def test_db03_manager_cannot_transfer_membership_between_managed_organizations(
    postgres_db_session,
):
    db = postgres_db_session
    owner = _create_user(db, "transfer-owner")
    organization_a = _create_organization(db, owner)
    organization_b = _create_organization(db, owner)

    target = _create_user(db, "transfer-target")
    _authenticate(db, owner)

    membership = create_membership(
        db,
        organization_id=organization_a.id,
        actor_user_id=owner.id,
        user_id=target.id,
        role="member",
    )

    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(
                update(OrganizationMembership)
                .where(OrganizationMembership.id == membership.id)
                .values(organization_id=organization_b.id)
            )


@pytest.mark.xfail(
    strict=True,
    reason="DB-04: current UPDATE policy does not protect membership user_id",
)
def test_db04_manager_cannot_change_membership_user_id_directly(
    postgres_db_session,
):
    db = postgres_db_session
    owner = _create_user(db, "change-user-owner")
    organization = _create_organization(db, owner)
    original_user = _create_user(db, "original-member")
    replacement_user = _create_user(db, "replacement-member")

    _authenticate(db, owner)
    membership = create_membership(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=original_user.id,
        role="member",
    )

    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(
                update(OrganizationMembership)
                .where(OrganizationMembership.id == membership.id)
                .values(user_id=replacement_user.id)
            )


@pytest.mark.xfail(
    strict=True,
    reason="DB-05: current UPDATE policy does not protect organization creator",
)
def test_db05_manager_cannot_change_organization_creator_directly(
    postgres_db_session,
):
    db = postgres_db_session
    owner = _create_user(db, "creator-owner")
    replacement_creator = _create_user(db, "replacement-creator")
    organization = _create_organization(db, owner)

    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(
                update(Organization)
                .where(Organization.id == organization.id)
                .values(created_by_user_id=replacement_creator.id)
            )


@pytest.mark.xfail(
    strict=True,
    reason="DB-06: current UPDATE policy does not protect the last active owner",
)
def test_db06_owner_cannot_deactivate_last_owner_directly(
    postgres_db_session,
):
    db = postgres_db_session
    owner = _create_user(db, "last-owner-deactivate")
    organization = _create_organization(db, owner)

    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(
                update(OrganizationMembership)
                .where(
                    OrganizationMembership.organization_id == organization.id,
                    OrganizationMembership.user_id == owner.id,
                    OrganizationMembership.role == "owner",
                    OrganizationMembership.is_active.is_(True),
                )
                .values(is_active=False)
            )


@pytest.mark.xfail(
    strict=True,
    reason="DB-07: current UPDATE policy does not protect the last active owner",
)
def test_db07_owner_cannot_demote_last_owner_directly(
    postgres_db_session,
):
    db = postgres_db_session
    owner = _create_user(db, "last-owner-demote")
    organization = _create_organization(db, owner)

    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(
                update(OrganizationMembership)
                .where(
                    OrganizationMembership.organization_id == organization.id,
                    OrganizationMembership.user_id == owner.id,
                    OrganizationMembership.role == "owner",
                    OrganizationMembership.is_active.is_(True),
                )
                .values(role="member")
            )



