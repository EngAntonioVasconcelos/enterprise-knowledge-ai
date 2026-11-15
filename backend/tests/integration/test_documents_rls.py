import uuid

import pytest
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.db.context import set_organization_context, set_worker_context
from app.models import Document, DocumentVersion
from app.services import document_service as documents
from app.services.connection_service import create_connection
from app.services.document_service import content_hash, normalize_content
from scripts.prepare_test_database import TEST_ADMIN_URL
from tests.integration.test_postgres_rls import (
    _authenticate,
    _create_organization,
    _create_user,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def docs_db(postgres_engine):
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


def _setup(db):
    """An organization with a Drive connection; the session ends as worker."""
    owner = _create_user(db, "docs-owner")
    organization = _create_organization(db, owner)
    _authenticate(db, owner)
    set_organization_context(db, organization_id=organization.id)
    connection = create_connection(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        provider="google_drive",
        name="Drive",
        settings={},
    )
    db.flush()
    ids = (owner.id, organization.id, connection.id)
    _as_worker(db, organization.id)
    return ids


def _as_worker(db, organization_id):
    db.flush()
    db.execute(text("SET ROLE eka_worker"))
    db.info.clear()
    set_worker_context(db, organization_id=organization_id)
    db.expire_all()


def _ingest(db, organization_id, connection_id, body, external_id="file-1"):
    document = documents.upsert_document(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
        external_id=external_id,
        title="Policy",
    )
    version = documents.add_version(
        db,
        document=document,
        content_hash=content_hash(normalize_content(body)),
    )
    return document, version


def test_the_worker_ingests_and_the_database_numbers_versions(docs_db):
    db = docs_db
    _, organization_id, connection_id = _setup(db)

    document, first = _ingest(db, organization_id, connection_id, "v1")
    documents.mark_version_ready(db, first)
    documents.activate_version(db, document=document, version=first)
    _, second = _ingest(db, organization_id, connection_id, "v2")

    assert (first.version_number, second.version_number) == (1, 2)
    db.expire_all()
    stored = db.get(Document, document.id)
    assert (stored.status, stored.current_version_id) == ("active", first.id)
    assert db.get(DocumentVersion, first.id).ready_at is not None


def test_only_a_ready_version_of_the_same_document_becomes_current(docs_db):
    db = docs_db
    _, organization_id, connection_id = _setup(db)
    document, processing = _ingest(db, organization_id, connection_id, "v1")
    other, other_version = _ingest(
        db, organization_id, connection_id, "x", external_id="file-2"
    )
    documents.mark_version_ready(db, other_version)
    db.flush()

    rule = "the current version must be a ready version"
    row = Document.id == document.id
    _refused(
        db,
        update(Document).where(row).values(current_version_id=processing.id),
        rule,
    )
    _refused(
        db,
        update(Document)
        .where(row)
        .values(current_version_id=other_version.id),
        rule,
    )
    _refused(
        db,
        update(Document).where(row).values(status="active"),
        "ck_documents_active_has_version",
    )


def test_a_processed_version_never_changes(docs_db):
    db = docs_db
    _, organization_id, connection_id = _setup(db)
    _, version = _ingest(db, organization_id, connection_id, "v1")
    documents.mark_version_ready(db, version)
    db.flush()
    row = DocumentVersion.id == version.id

    _refused(
        db,
        update(DocumentVersion).where(row).values(status="failed"),
        "a processed document version cannot change",
    )
    _refused(
        db,
        update(DocumentVersion).where(row).values(content_hash="0" * 64),
        "permission denied",
    )
    _refused(db, text("DELETE FROM document_versions"), "permission denied")


def test_the_worker_writes_only_for_the_organization_of_its_job(docs_db):
    db = docs_db
    _, organization_id, connection_id = _setup(db)
    document, _ = _ingest(db, organization_id, connection_id, "v1")
    document_id = document.id

    _as_worker(db, uuid.uuid4())
    assert db.scalars(
        select(Document.id).where(Document.id == document_id)
    ).all() == []

    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            documents.upsert_document(
                db,
                organization_id=organization_id,
                connection_id=connection_id,
                external_id="file-9",
                title="Elsewhere",
            )
    assert "row-level security" in str(error.value.orig)


def test_without_source_permission_even_the_owner_sees_nothing(docs_db):
    # Strict rule (migration a2d7c4e9f1b6): reading follows the source's
    # permissions, for owners and admins too.
    db = docs_db
    owner_id, organization_id, connection_id = _setup(db)
    document, _ = _ingest(db, organization_id, connection_id, "v1")
    document_id = document.id
    db.flush()

    db.execute(text("SET ROLE eka_runtime"))
    db.info.clear()
    db.info.update(
        {
            "auth_issuer": None,
            "auth_subject": None,
            "user_id": None,
            "organization_id": None,
        }
    )
    owner = type("Owner", (), {"id": owner_id})()
    _authenticate(db, owner)
    db.expire_all()

    assert db.scalars(
        select(Document.id).where(Document.id == document_id)
    ).all() == []
    _refused(
        db,
        update(Document).where(Document.id == document_id).values(title="x"),
        "permission denied",
    )

    stranger = _create_user(db, "docs-stranger")
    _authenticate(db, stranger)
    db.expire_all()
    assert db.scalars(
        select(Document.id).where(Document.id == document_id)
    ).all() == []
