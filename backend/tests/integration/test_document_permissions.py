import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.db.context import set_organization_context, set_worker_context
from app.models import Document, DocumentAccess, DocumentVersion
from app.services import document_service as documents
from app.services.connection_service import create_connection, update_connection
from app.services.document_permission_service import (
    SourcePermission,
    document_statistics,
    list_documents,
    replace_document_permissions,
)
from app.services.document_service import content_hash, normalize_content
from app.services.membership_service import deactivate_membership
from scripts.prepare_test_database import TEST_ADMIN_URL
from tests.integration.test_postgres_rls import (
    _SUBJECTS,
    _authenticate_as,
    _create_organization,
    _provision_user,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def perm_db(postgres_engine):
    # One administrator connection that plays the API (SET ROLE eka_runtime)
    # and the worker (SET ROLE eka_worker) on the same uncommitted data.
    engine = create_engine(TEST_ADMIN_URL)
    connection = engine.connect()
    transaction = connection.begin()
    db = sessionmaker(
        bind=connection,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )()

    try:
        db.execute(text("SET ROLE eka_runtime"))
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def _refused(db, statement, fragment):
    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            db.execute(statement)
    assert fragment in str(error.value.orig)


def _user(db, email):
    subject = f"test-subject-{uuid.uuid4().hex}"
    user = _provision_user(db, subject=subject, email=email)
    _SUBJECTS[user.id] = subject
    return user.id


def _as_runtime(db, user_id):
    db.flush()
    db.execute(text("SET ROLE eka_runtime"))
    db.info.clear()
    _authenticate_as(db, user_id)
    db.expire_all()


def _as_worker(db, organization_id):
    db.flush()
    db.execute(text("SET ROLE eka_worker"))
    db.info.clear()
    set_worker_context(db, organization_id=organization_id)
    db.expire_all()


def _set_membership(db, organization_id, user_id, *, active=True):
    """Add or (de)activate a member as the administrator connection.

    The scenario is built this way because the API cannot see accounts
    outside the organization; the triggers under test run all the same.
    """
    db.flush()
    db.execute(text("RESET ROLE"))
    updated = db.execute(
        text(
            "UPDATE organization_memberships SET is_active = :active, "
            "updated_at = now() "
            "WHERE organization_id = :organization AND user_id = :user"
        ),
        {"active": active, "organization": organization_id, "user": user_id},
    ).rowcount
    if not updated:
        db.execute(
            text(
                "INSERT INTO organization_memberships (id, organization_id, "
                "user_id, role, is_active, has_held_privileged_role, "
                "has_held_owner_role, created_at, updated_at) VALUES "
                "(gen_random_uuid(), :organization, :user, 'member', "
                ":active, false, false, now(), now())"
            ),
            {
                "active": active,
                "organization": organization_id,
                "user": user_id,
            },
        )
    db.execute(text("SET ROLE eka_runtime"))
    db.expire_all()


class World:
    """An organization at acme.test with an owner, two members and an
    outsider who has an account but is not a member."""

    def __init__(self, db):
        unique = uuid.uuid4().hex[:8]
        self.domain = f"acme-{unique}.test"
        self.owner = _user(db, f"owner@{self.domain}")
        self.ana = _user(db, f"ana@{self.domain}")
        self.rui = _user(db, f"rui@{self.domain}")
        self.outsider_email = f"outsider-{unique}@other.test"
        self.outsider = _user(db, self.outsider_email)

        _authenticate_as(db, self.owner)
        organization = _create_organization(
            db, SimpleNamespace(id=self.owner)
        )
        self.organization = organization.id
        for member in (self.ana, self.rui):
            _set_membership(db, self.organization, member)
        _authenticate_as(db, self.owner)
        set_organization_context(db, organization_id=self.organization)
        self.connection = create_connection(
            db,
            organization_id=self.organization,
            actor_user_id=self.owner,
            provider="google_drive",
            name="Drive",
            settings={},
        ).id
        db.flush()

    def document(self, db, permissions, external_id=None):
        """Ingest a ready document with these source permissions."""
        _as_worker(db, self.organization)
        document = documents.upsert_document(
            db,
            organization_id=self.organization,
            connection_id=self.connection,
            external_id=external_id or uuid.uuid4().hex,
            title=f"Document {uuid.uuid4().hex[:6]}",
        )
        version = documents.add_version(
            db,
            document=document,
            content_hash=content_hash(normalize_content(uuid.uuid4().hex)),
        )
        documents.mark_version_ready(db, version)
        documents.activate_version(db, document=document, version=version)
        replace_document_permissions(
            db, document=document, permissions=permissions
        )
        db.flush()
        return document.id

    def readers(self, db, document_id):
        visible = []
        for name in ("owner", "ana", "rui", "outsider"):
            _as_runtime(db, getattr(self, name))
            found = db.scalars(
                select(Document.id).where(Document.id == document_id)
            ).all()
            if found:
                visible.append(name)
        return visible


@pytest.fixture
def world(perm_db):
    return World(perm_db)


def test_a_user_grant_opens_the_document_to_that_person_only(perm_db, world):
    db = perm_db
    document = world.document(
        db, [SourcePermission("user", f"Ana@{world.domain}")]
    )

    # Strict rule: the owner of the organization does not see it either.
    assert world.readers(db, document) == ["ana"]


def test_domain_and_organization_grants(perm_db, world):
    db = perm_db
    by_domain = world.document(
        db, [SourcePermission("domain", world.domain)]
    )
    everyone = world.document(db, [SourcePermission("organization")])

    assert world.readers(db, by_domain) == ["owner", "ana", "rui"]
    assert world.readers(db, everyone) == ["owner", "ana", "rui"]


def test_unresolved_grants_give_no_access(perm_db, world):
    db = perm_db
    group = world.document(
        db, [SourcePermission("group", f"finance@{world.domain}")]
    )
    link = world.document(db, [SourcePermission("anyone")])
    nobody = world.document(db, [])

    assert world.readers(db, group) == []
    assert world.readers(db, link) == []
    assert world.readers(db, nobody) == []


def test_link_sharing_counts_only_when_an_admin_says_so(perm_db, world):
    db = perm_db
    link = world.document(db, [SourcePermission("anyone")])
    assert world.readers(db, link) == []

    _as_runtime(db, world.owner)
    set_organization_context(db, organization_id=world.organization)
    update_connection(
        db,
        organization_id=world.organization,
        connection_id=world.connection,
        settings={"link_sharing_grants_organization": True},
    )
    db.flush()

    assert world.readers(db, link) == ["owner", "ana", "rui"]


def test_an_outsider_with_a_matching_email_gets_nothing(perm_db, world):
    db = perm_db
    document = world.document(
        db, [SourcePermission("user", world.outsider_email)]
    )

    assert world.readers(db, document) == []


def test_leaving_removes_access_at_once_and_coming_back_restores_it(
    perm_db, world
):
    db = perm_db
    document = world.document(
        db, [SourcePermission("domain", world.domain)]
    )

    # Through the real service, as the owner would.
    _as_runtime(db, world.owner)
    set_organization_context(db, organization_id=world.organization)
    deactivate_membership(
        db,
        organization_id=world.organization,
        actor_user_id=world.owner,
        user_id=world.rui,
    )
    db.flush()
    assert world.readers(db, document) == ["owner", "ana"]

    _set_membership(db, world.organization, world.rui, active=True)
    assert world.readers(db, document) == ["owner", "ana", "rui"]


def test_a_new_member_gets_what_the_permissions_already_allow(
    perm_db, world
):
    db = perm_db
    document = world.document(
        db, [SourcePermission("domain", world.domain)]
    )
    _as_runtime(db, world.owner)
    newcomer = _user(db, f"newcomer@{world.domain}")
    assert newcomer not in [world.ana, world.rui]

    _set_membership(db, world.organization, newcomer)

    _as_runtime(db, newcomer)
    assert db.scalars(
        select(Document.id).where(Document.id == document)
    ).all() == [document]


def test_versions_follow_the_document(perm_db, world):
    db = perm_db
    document = world.document(
        db, [SourcePermission("user", f"ana@{world.domain}")]
    )

    for user, expected in ((world.ana, 1), (world.rui, 0)):
        _as_runtime(db, user)
        assert len(
            db.scalars(
                select(DocumentVersion.id).where(
                    DocumentVersion.document_id == document
                )
            ).all()
        ) == expected


def test_managers_get_counts_not_titles(perm_db, world):
    db = perm_db
    world.document(db, [SourcePermission("user", f"ana@{world.domain}")])
    world.document(db, [SourcePermission("user", f"ana@{world.domain}")])

    _as_runtime(db, world.owner)
    assert list_documents(db, organization_id=world.organization) == []
    assert document_statistics(db, organization_id=world.organization) == {
        "total": 2,
        "by_status": {"active": 2},
    }

    _as_runtime(db, world.ana)
    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            document_statistics(db, organization_id=world.organization)
    assert "only owners and admins" in str(error.value.orig)


def test_nobody_writes_readers_directly(perm_db, world):
    db = perm_db
    document = world.document(db, [])

    _as_runtime(db, world.ana)
    _refused(
        db,
        insert(DocumentAccess).values(
            document_id=document,
            user_id=world.ana,
            organization_id=world.organization,
        ),
        "permission denied",
    )

    _as_worker(db, world.organization)
    _refused(
        db,
        insert(DocumentAccess).values(
            document_id=document,
            user_id=world.ana,
            organization_id=world.organization,
        ),
        "permission denied",
    )


def test_the_worker_resolves_only_its_own_organization(perm_db, world):
    db = perm_db
    document = world.document(db, [SourcePermission("organization")])

    _as_worker(db, uuid.uuid4())
    _refused(
        db,
        text("SELECT app_private.resolve_document_access(:id)").bindparams(
            id=document
        ),
        "another organization",
    )
