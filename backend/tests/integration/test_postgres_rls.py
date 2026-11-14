import threading
import uuid

import pytest
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.context import (
    CONTEXT_KEYS,
    set_authentication_context,
    set_identity_context,
    set_organization_context,
)
from app.models import (
    AuthenticationIdentity,
    Organization,
    OrganizationMembership,
    User,
)
from app.services.authentication_service import (
    resolve_authenticated_user,
)
from app.services.membership_service import (
    create_membership,
    update_membership_role,
)
from app.services.organization_service import create_organization
from app.services.organization_user_service import (
    create_organization_user,
)


pytestmark = pytest.mark.integration

TEST_ISSUER = "https://test-identity.example.com/"


_SUBJECTS = {}


def _apply_context(db, context):
    db.info.update(context)
    db.execute(
        text("""
            SELECT
                set_config('app.auth_issuer', :auth_issuer, true),
                set_config('app.auth_subject', :auth_subject, true),
                set_config('app.user_id', :user_id, true),
                set_config('app.organization_id', :organization_id, true)
        """),
        {key: str(value or "") for key, value in context.items()},
    )


def _provision_user(db, *, subject, email):
    # Accounts are created by the same database function the login flow
    # uses. The caller's context is restored afterwards.
    saved = {key: db.info.get(key) for key in CONTEXT_KEYS}

    set_authentication_context(db, issuer=TEST_ISSUER, subject=subject)
    user_id = db.scalar(
        text("SELECT app_private.provision_user(:email, :full_name)"),
        {"email": email, "full_name": "RLS Integration Test User"},
    )
    user = db.get(User, user_id)

    _apply_context(db, saved)

    return user


def _create_user(db, prefix="rls-user"):
    unique = uuid.uuid4().hex
    subject = f"test-subject-{unique}"

    user = _provision_user(
        db,
        subject=subject,
        email=f"{prefix}-{unique}@example.com",
    )
    _SUBJECTS[user.id] = subject

    return user


def _authenticate_as(db, user_id):
    set_identity_context(
        db,
        issuer=TEST_ISSUER,
        subject=_SUBJECTS[user_id],
        user_id=user_id,
    )


def _authenticate(db, user):
    _authenticate_as(db, user.id)


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
    owner = _create_user(db, "inactive-owner")
    member = _create_user(db, "inactive-member")
    organization = _create_organization(db, owner)

    _authenticate(db, owner)
    membership = create_membership(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=member.id,
        role="member",
    )

    membership.is_active = False
    db.flush()

    _authenticate(db, member)

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

def test_db02_admin_cannot_insert_admin_directly(postgres_db_session):
    db = postgres_db_session
    _, admin, organization = _create_admin_context(db)
    target = _create_user(db, "direct-admin-target")

    with pytest.raises(DBAPIError) as exc_info:
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

    assert "row-level security" in str(exc_info.value.orig).lower()


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

    with pytest.raises(DBAPIError, match="membership identity is immutable"):
        with db.begin_nested():
            db.execute(
                update(OrganizationMembership)
                .where(OrganizationMembership.id == membership.id)
                .values(organization_id=organization_b.id)
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

    with pytest.raises(DBAPIError, match="membership identity is immutable"):
        with db.begin_nested():
            db.execute(
                update(OrganizationMembership)
                .where(OrganizationMembership.id == membership.id)
                .values(user_id=replacement_user.id)
            )


def test_db05_manager_cannot_change_organization_creator_directly(
    postgres_db_session,
):
    db = postgres_db_session
    owner = _create_user(db, "creator-owner")
    replacement_creator = _create_user(db, "replacement-creator")
    organization = _create_organization(db, owner)

    with pytest.raises(DBAPIError, match="organization identity and creator are immutable"):
        with db.begin_nested():
            db.execute(
                update(Organization)
                .where(Organization.id == organization.id)
                .values(created_by_user_id=replacement_creator.id)
            )


def test_db06_owner_cannot_deactivate_last_owner_directly(
    postgres_db_session,
):
    db = postgres_db_session
    owner = _create_user(db, "last-owner-deactivate")
    organization = _create_organization(db, owner)

    with pytest.raises(DBAPIError, match="at least one active owner"):
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


def test_db07_owner_cannot_demote_last_owner_directly(
    postgres_db_session,
):
    db = postgres_db_session
    owner = _create_user(db, "last-owner-demote")
    organization = _create_organization(db, owner)

    with pytest.raises(DBAPIError, match="at least one active owner"):
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


def test_db08_membership_role_history_cannot_be_erased(postgres_db_session):
    db = postgres_db_session
    owner = _create_user(db, "history-owner")
    former_admin = _create_user(db, "history-former-admin")
    organization = _create_organization(db, owner)

    _authenticate(db, owner)
    create_membership(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=former_admin.id,
        role="admin",
    )
    membership = update_membership_role(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=former_admin.id,
        role="member",
    )
    assert membership.has_held_privileged_role is True

    with pytest.raises(DBAPIError, match="role history cannot be erased"):
        with db.begin_nested():
            db.execute(
                update(OrganizationMembership)
                .where(OrganizationMembership.id == membership.id)
                .values(has_held_privileged_role=False)
            )


def test_db09_last_owner_is_protected_under_concurrency(postgres_engine):
    # Two owners give up ownership at the same time, on separate
    # connections. Each one alone is allowed; together they would leave the
    # organization without an owner. Exactly one must be rejected.
    #
    # This test commits its data: concurrency cannot be observed inside a
    # single rolled-back transaction. The rows stay in the disposable test
    # database, under unique names.
    with Session(postgres_engine) as setup:
        owner_a = _create_user(setup, "concurrent-owner-a")
        owner_b = _create_user(setup, "concurrent-owner-b")
        organization = _create_organization(setup, owner_a)
        create_membership(
            setup,
            organization_id=organization.id,
            actor_user_id=owner_a.id,
            user_id=owner_b.id,
            role="owner",
        )
        setup.commit()

        organization_id = organization.id
        owner_a_id = owner_a.id
        owner_b_id = owner_b.id

    def give_up_ownership(session, user_id):
        _authenticate_as(session, user_id)
        session.execute(text("SET LOCAL lock_timeout = '15s'"))
        session.execute(
            update(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user_id,
            )
            .values(role="member")
        )

    second_outcome = {}

    def second_owner_gives_up():
        with Session(postgres_engine) as second:
            try:
                give_up_ownership(second, owner_b_id)
                second.commit()
                second_outcome["error"] = None
            except DBAPIError as exc:
                second.rollback()
                second_outcome["error"] = str(exc.orig)

    with Session(postgres_engine) as first:
        give_up_ownership(first, owner_a_id)

        worker = threading.Thread(target=second_owner_gives_up)
        worker.start()
        worker.join(timeout=1)

        # The second transaction must be waiting for the first to finish.
        assert worker.is_alive()

        first.commit()

    worker.join(timeout=20)
    assert not worker.is_alive()

    assert second_outcome["error"] is not None
    assert "at least one active owner" in second_outcome["error"]

    with Session(postgres_engine) as check:
        _authenticate_as(check, owner_b_id)

        active_owners = check.scalars(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == "owner",
                OrganizationMembership.is_active.is_(True),
            )
        ).all()

    assert [m.user_id for m in active_owners] == [owner_b_id]


def _visible_user_ids(db, *users):
    return set(
        db.scalars(
            select(User.id).where(User.id.in_([user.id for user in users]))
        )
    )


def test_users_are_invisible_without_identity_context(postgres_db_session):
    db = postgres_db_session
    user = _create_user(db, "identity-hidden")

    _clear_database_context(db)

    assert _visible_user_ids(db, user) == set()


def test_user_reads_own_account_but_not_a_strangers(postgres_db_session):
    db = postgres_db_session
    user = _create_user(db, "identity-self")
    stranger = _create_user(db, "identity-stranger")

    _authenticate(db, user)

    assert _visible_user_ids(db, user, stranger) == {user.id}


def test_only_managers_read_accounts_of_their_organization(
    postgres_db_session,
):
    db = postgres_db_session
    owner = _create_user(db, "directory-owner")
    member = _create_user(db, "directory-member")
    other_owner = _create_user(db, "directory-other-owner")
    organization = _create_organization(db, owner)
    _create_organization(db, other_owner)

    _authenticate(db, owner)
    create_membership(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=member.id,
        role="member",
    )

    everyone = (owner, member, other_owner)

    assert _visible_user_ids(db, *everyone) == {owner.id, member.id}

    _authenticate(db, member)
    assert _visible_user_ids(db, *everyone) == {member.id}

    _authenticate(db, other_owner)
    assert _visible_user_ids(db, *everyone) == {other_owner.id}


def test_login_resolves_only_the_presented_identity(postgres_db_session):
    db = postgres_db_session
    user = _create_user(db, "login-user")
    other = _create_user(db, "login-other")

    _clear_database_context(db)
    db.info.update({key: None for key in CONTEXT_KEYS})

    assert resolve_authenticated_user(
        db, issuer=TEST_ISSUER, subject=_SUBJECTS[user.id]
    ) is None

    set_authentication_context(
        db, issuer=TEST_ISSUER, subject=_SUBJECTS[user.id]
    )

    resolved = resolve_authenticated_user(
        db, issuer=TEST_ISSUER, subject=_SUBJECTS[user.id]
    )
    assert resolved is not None
    assert resolved.id == user.id

    assert resolve_authenticated_user(
        db, issuer=TEST_ISSUER, subject=_SUBJECTS[other.id]
    ) is None


def test_identities_of_other_users_are_never_visible(postgres_db_session):
    db = postgres_db_session
    owner = _create_user(db, "identity-owner")
    member = _create_user(db, "identity-member")
    organization = _create_organization(db, owner)

    _authenticate(db, owner)
    create_membership(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=member.id,
        role="member",
    )

    visible = db.scalars(select(AuthenticationIdentity.user_id)).all()

    assert visible == [owner.id]


def test_runtime_cannot_write_identities_or_update_accounts(
    postgres_db_session,
):
    db = postgres_db_session
    user = _create_user(db, "identity-write")
    _authenticate(db, user)

    with pytest.raises(DBAPIError, match="permission denied"):
        with db.begin_nested():
            db.execute(
                insert(AuthenticationIdentity).values(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    issuer=TEST_ISSUER,
                    subject="forged-subject",
                    is_active=True,
                )
            )

    with pytest.raises(DBAPIError, match="permission denied"):
        with db.begin_nested():
            db.execute(
                update(User)
                .where(User.id == user.id)
                .values(email="taken-over@example.com")
            )


def test_provisioning_requires_a_verified_identity(postgres_db_session):
    db = postgres_db_session

    with pytest.raises(DBAPIError, match="authenticated identity"):
        with db.begin_nested():
            db.execute(
                text("SELECT app_private.provision_user(:email, :name)"),
                {"email": "nobody@example.com", "name": "Nobody"},
            )


def test_provisioning_is_idempotent_and_links_by_email(postgres_db_session):
    db = postgres_db_session
    unique = uuid.uuid4().hex
    email = f"provisioned-{unique}@example.com"

    first = _provision_user(db, subject=f"first-{unique}", email=email)
    again = _provision_user(
        db, subject=f"first-{unique}", email=email.upper()
    )
    linked = _provision_user(db, subject=f"second-{unique}", email=email)

    assert first.email == email
    assert again.id == first.id
    assert linked.id == first.id


def test_only_managers_can_create_an_account_for_their_organization(
    postgres_db_session,
):
    db = postgres_db_session
    owner = _create_user(db, "account-owner")
    member = _create_user(db, "account-member")
    organization = _create_organization(db, owner)

    _authenticate(db, owner)
    set_organization_context(db, organization_id=organization.id)
    create_membership(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        user_id=member.id,
        role="member",
    )

    unique = uuid.uuid4().hex
    created, membership = create_organization_user(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        email=f"account-new-{unique}@example.com",
        full_name="Added By Owner",
    )
    assert membership.user_id == created.id
    assert _visible_user_ids(db, created) == {created.id}

    _authenticate(db, member)
    set_organization_context(db, organization_id=organization.id)

    with pytest.raises(DBAPIError, match="row-level security"):
        with db.begin_nested():
            db.execute(
                insert(User).values(
                    id=uuid.uuid4(),
                    email=f"account-forged-{unique}@example.com",
                    full_name="Forged Account",
                    is_active=True,
                )
            )
