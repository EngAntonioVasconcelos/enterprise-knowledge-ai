import uuid

import pytest
from sqlalchemy import select

from app.models.data_connection import DataConnection
from app.models.document_access import DocumentPermission
from app.models.membership import OrganizationMembership
from app.models.user import User
from app.services import document_service as documents
from app.services.document_permission_service import (
    InvalidPermissionError,
    SourcePermission,
    replace_document_permissions,
)


def test_permissions_are_normalized_and_checked():
    assert SourcePermission("User", " Ana@Example.COM ", "Writer").normalized() == (
        SourcePermission("user", "ana@example.com", "writer")
    )
    assert SourcePermission("anyone", "ignored").normalized().principal == ""
    assert SourcePermission("domain", "Example.com").normalized().principal == (
        "example.com"
    )

    for bad in (
        SourcePermission("robot", "x@example.com"),
        SourcePermission("user", "not-an-email"),
        SourcePermission("domain", "ana@example.com"),
        SourcePermission("user", "ana@example.com", "emperor"),
    ):
        with pytest.raises(InvalidPermissionError):
            bad.normalized()


@pytest.fixture
def organization(client, db_session):
    unique = uuid.uuid4().hex[:8]
    created = client.post(
        "/api/v1/organizations/",
        json={"name": f"Perm Org {unique}", "slug": f"perm-{unique}"},
    ).json()
    connection = client.post(
        f"/api/v1/organizations/{created['id']}/connections/",
        json={"provider": "google_drive", "name": "Drive"},
    ).json()
    return created["id"], db_session.get(
        DataConnection, uuid.UUID(connection["id"])
    )


def _document(db, connection, external_id="file-1", title="Handbook"):
    return documents.upsert_document(
        db,
        organization_id=connection.organization_id,
        connection_id=connection.id,
        external_id=external_id,
        title=title,
    )


def test_the_strongest_role_per_principal_is_kept(db_session, organization):
    _, connection = organization
    document = _document(db_session, connection)

    replace_document_permissions(
        db_session,
        document=document,
        permissions=[
            SourcePermission("user", "ana@example.com", "reader"),
            SourcePermission("user", "ANA@example.com", "writer"),
            SourcePermission("domain", "example.com"),
        ],
    )
    db_session.commit()

    rows = db_session.scalars(
        select(DocumentPermission).order_by(DocumentPermission.principal_type)
    ).all()
    assert [(r.principal_type, r.principal, r.role) for r in rows] == [
        ("domain", "example.com", "reader"),
        ("user", "ana@example.com", "writer"),
    ]

    # Replacing drops what the source no longer grants.
    replace_document_permissions(db_session, document=document, permissions=[])
    db_session.commit()
    assert db_session.scalars(select(DocumentPermission)).all() == []


def _member(db_session, organization_id, role):
    user = User(
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.com",
        full_name=f"Org {role}",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(
        OrganizationMembership(
            organization_id=uuid.UUID(organization_id),
            user_id=user.id,
            role=role,
            is_active=True,
            has_held_privileged_role=role in {"owner", "admin"},
            has_held_owner_role=role == "owner",
        )
    )
    db_session.commit()
    return user


def test_members_list_documents_and_only_managers_see_statistics(
    client, client_for_user, db_session, organization
):
    organization_id, connection = organization
    _document(db_session, connection, external_id="a", title="B doc")
    _document(db_session, connection, external_id="b", title="A doc")
    db_session.commit()
    base = f"/api/v1/organizations/{organization_id}/documents"

    statistics = client.get(f"{base}/statistics").json()
    assert statistics == {"total": 2, "by_status": {"pending": 2}}

    viewer = _member(db_session, organization_id, "viewer")
    with client_for_user(viewer) as other:
        # Unit tests run on SQLite, without row-level security: here the
        # list is unfiltered; filtering is proven in the integration tests.
        titles = [d["title"] for d in other.get(f"{base}/").json()]
        assert titles == ["A doc", "B doc"]
        assert other.get(f"{base}/statistics").status_code == 403


def test_an_unknown_document_is_not_found(client, organization):
    organization_id, _ = organization

    response = client.get(
        f"/api/v1/organizations/{organization_id}/documents/{uuid.uuid4()}"
    )

    assert response.status_code == 404


def test_a_document_page_shows_the_first_passages_and_a_failed_reading(
    client, db_session, organization
):
    from app.models.document_chunk import DocumentChunk

    organization_id, connection = organization
    document = _document(db_session, connection, external_id="p", title="Manual")
    version = documents.add_version(db_session, document=document, content_hash="h1")
    documents.mark_version_ready(db_session, version)
    documents.activate_version(db_session, document=document, version=version)
    long = "word " * 400
    for ordinal, content in enumerate(["Ferias: 25 dias.", long, "Terceiro.", "Quarto."]):
        db_session.add(
            DocumentChunk(
                organization_id=document.organization_id,
                document_id=document.id,
                version_id=version.id,
                ordinal=ordinal,
                heading="1. Ferias" if ordinal == 0 else None,
                content=content,
                start_char=0,
                end_char=len(content),
                token_estimate=1,
            )
        )
    newer = documents.add_version(db_session, document=document, content_hash="h2")
    documents.fail_version(db_session, newer, error="The PDF could not be read")
    db_session.commit()

    base = f"/api/v1/organizations/{organization_id}/documents/{document.id}/page"
    page = client.get(base).json()
    assert page["document"]["title"] == "Manual"
    assert page["passages"] == 4
    assert [p["content"] for p in page["excerpt"]][0] == "Ferias: 25 dias."
    assert page["excerpt"][0]["heading"] == "1. Ferias"
    # Three passages at most, each cut short.
    assert len(page["excerpt"]) == 3
    assert len(page["excerpt"][1]["content"]) <= 701
    assert page["failure"] == "The PDF could not be read"
    assert page["read_at"] is not None

    unknown = f"/api/v1/organizations/{organization_id}/documents/{uuid.uuid4()}/page"
    assert client.get(unknown).status_code == 404
