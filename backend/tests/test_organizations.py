
import uuid

from sqlalchemy import select

from app.models.membership import OrganizationMembership

from app.models.organization import Organization
from app.models.user import User

def test_create_organization(
    client,
    db_session,
    authenticated_user,
):
    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Test Organization",
            "slug": "test-organization",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["name"] == "Test Organization"
    assert data["slug"] == "test-organization"

    organization_id = uuid.UUID(data["id"])

    assert "created_at" in data

    membership = db_session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == authenticated_user.id,
        )
    )

    assert membership is not None
    assert membership.is_active is True
    assert membership.role == "owner"


def test_create_duplicate_organization(client):
    payload = {
        "name": "Test Organization",
        "slug": "test-organization",
    }

    first_response = client.post(
        "/api/v1/organizations/",
        json=payload,
    )

    second_response = client.post(
        "/api/v1/organizations/",
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409

    assert second_response.json() == {
        "detail": "Organization slug already exists."
    }


def test_create_organization_with_short_name(client):
    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "A",
            "slug": "valid-slug",
        },
    )

    assert response.status_code == 422


def test_create_organization_with_short_slug(client):
    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Valid Organization",
            "slug": "a",
        },
    )

    assert response.status_code == 422


def test_create_organization_without_name(client):
    response = client.post(
        "/api/v1/organizations/",
        json={
            "slug": "valid-slug",
        },
    )

    assert response.status_code == 422

def test_root_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200

    data = response.json()

    assert data["message"] == "Welcome to Enterprise Knowledge AI API"
    assert data["version"] == "0.1.0"
    assert data["status"] == "running"


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "healthy"
    assert data["service"] == "enterprise-knowledge-ai-api"

def test_list_organizations_empty(client):
    response = client.get("/api/v1/organizations/")

    assert response.status_code == 200
    assert response.json() == []


def test_list_organizations(client):
    first_response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "First Organization",
            "slug": "first-organization",
        },
    )

    second_response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Second Organization",
            "slug": "second-organization",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    response = client.get("/api/v1/organizations/")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_organizations_with_pagination(client):
    for number in range(3):
        response = client.post(
            "/api/v1/organizations/",
            json={
                "name": f"Organization {number}",
                "slug": f"organization-{number}",
            },
        )
        assert response.status_code == 201

    response = client.get(
        "/api/v1/organizations/?skip=1&limit=1"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_organizations_rejects_invalid_pagination(client):
    negative_skip_response = client.get(
        "/api/v1/organizations/?skip=-1"
    )

    zero_limit_response = client.get(
        "/api/v1/organizations/?limit=0"
    )

    excessive_limit_response = client.get(
        "/api/v1/organizations/?limit=101"
    )

    assert negative_skip_response.status_code == 422
    assert zero_limit_response.status_code == 422
    assert excessive_limit_response.status_code == 422
  

def test_get_organization(client):
    create_response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Organization Details",
            "slug": "organization-details",
        },
    )

    assert create_response.status_code == 201

    organization_id = create_response.json()["id"]

    response = client.get(
        f"/api/v1/organizations/{organization_id}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == organization_id
    assert response.json()["name"] == "Organization Details"
    assert response.json()["slug"] == "organization-details"


def test_get_nonexistent_organization(client):
    nonexistent_id = str(uuid.uuid4())

    response = client.get(
        f"/api/v1/organizations/{nonexistent_id}"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Organization not found."
    }


def test_get_organization_with_invalid_uuid(client):
    response = client.get(
        "/api/v1/organizations/invalid-uuid"
    )

    assert response.status_code == 422

def test_update_organization_name(client):
    create_response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Original Organization",
            "slug": "original-organization",
        },
    )

    organization_id = create_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}",
        json={"name": "Updated Organization"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Organization"
    assert response.json()["slug"] == "original-organization"


def test_update_organization_slug(client):
    create_response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Original Organization",
            "slug": "original-organization",
        },
    )

    organization_id = create_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}",
        json={"slug": "updated-organization"},
    )

    assert response.status_code == 200
    assert response.json()["slug"] == "updated-organization"
    assert response.json()["name"] == "Original Organization"


def test_update_organization_all_fields(client):
    create_response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Original Organization",
            "slug": "original-organization",
        },
    )

    organization_id = create_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}",
        json={
            "name": "Updated Organization",
            "slug": "updated-organization",
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Organization"
    assert response.json()["slug"] == "updated-organization"


def test_update_nonexistent_organization(client):
    nonexistent_id = str(uuid.uuid4())

    response = client.patch(
        f"/api/v1/organizations/{nonexistent_id}",
        json={"name": "Updated Organization"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Organization not found."
    }


def test_update_organization_with_duplicate_slug(client):
    client.post(
        "/api/v1/organizations/",
        json={
            "name": "First Organization",
            "slug": "first-organization",
        },
    )

    second_response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Second Organization",
            "slug": "second-organization",
        },
    )

    organization_id = second_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}",
        json={"slug": "first-organization"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Organization slug already exists."
    }


def test_update_organization_rejects_empty_or_null_values(client):
    create_response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Original Organization",
            "slug": "original-organization",
        },
    )

    organization_id = create_response.json()["id"]

    empty_response = client.patch(
        f"/api/v1/organizations/{organization_id}",
        json={},
    )

    null_response = client.patch(
        f"/api/v1/organizations/{organization_id}",
        json={"name": None},
    )

    assert empty_response.status_code == 422
    assert null_response.status_code == 422


def test_create_organization_requires_authentication(
    unauthenticated_client,
):
    response = unauthenticated_client.post(
        "/api/v1/organizations/",
        json={
            "name": "Unauthorized Organization",
            "slug": "unauthorized-organization",
        },
    )

    assert response.status_code == 401

def test_list_organizations_only_returns_user_memberships(
    client,
    db_session,
    authenticated_user,
):
    other_user = User(
        email="other@example.com",
        full_name="Other User",
        is_active=True,
    )
    db_session.add(other_user)
    db_session.flush()

    organization = Organization(
        name="Other Organization",
        slug="other-organization",
    )
    db_session.add(organization)
    db_session.flush()

    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=other_user.id,
        role="owner",
        has_held_privileged_role=True,
        has_held_owner_role=True,
        is_active=True,
    )
    db_session.add(membership)
    db_session.commit()

    response = client.get("/api/v1/organizations/")

    assert response.status_code == 200

    organization_ids = [
        item["id"] for item in response.json()
    ]

    assert str(organization.id) not in organization_ids

def test_get_organization_rejects_non_member(
    client,
    db_session,
):
    other_user = User(
        email="nonmember@example.com",
        full_name="Non Member",
        is_active=True,
    )
    db_session.add(other_user)
    db_session.flush()

    organization = Organization(
        name="Private Organization",
        slug="private-organization",
    )
    db_session.add(organization)
    db_session.flush()

    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=other_user.id,
        role="owner",
        has_held_privileged_role=True,
        has_held_owner_role=True,
        is_active=True,
    )
    db_session.add(membership)
    db_session.commit()

    response = client.get(
        f"/api/v1/organizations/{organization.id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found."

def test_member_cannot_update_organization(
    client,
    db_session,
    authenticated_user,
):
    organization = Organization(
        name="Member Test Organization",
        slug="member-test-organization",
    )
    db_session.add(organization)
    db_session.flush()

    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=authenticated_user.id,
        role="member",
        is_active=True,
    )
    db_session.add(membership)
    db_session.commit()

    response = client.patch(
        f"/api/v1/organizations/{organization.id}",
        json={"name": "Updated Organization"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Insufficient organization permissions."
    )

def test_viewer_cannot_update_organization(
    client,
    db_session,
    authenticated_user,
):
    organization = Organization(
        name="Viewer Test Organization",
        slug="viewer-test-organization",
    )
    db_session.add(organization)
    db_session.flush()

    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=authenticated_user.id,
        role="viewer",
        is_active=True,
    )
    db_session.add(membership)
    db_session.commit()

    response = client.patch(
        f"/api/v1/organizations/{organization.id}",
        json={"name": "Updated Organization"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Insufficient organization permissions."
    )

def test_admin_can_update_organization(
    client,
    db_session,
    authenticated_user,
):
    organization = Organization(
        name="Admin Test Organization",
        slug="admin-test-organization",
    )
    db_session.add(organization)
    db_session.flush()

    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=authenticated_user.id,
        role="admin",
        has_held_privileged_role=True,
        is_active=True,
    )
    db_session.add(membership)
    db_session.commit()

    response = client.patch(
        f"/api/v1/organizations/{organization.id}",
        json={"name": "Updated by Admin"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated by Admin"

def test_owner_can_update_organization(
    client,
    db_session,
    authenticated_user,
):
    organization = Organization(
        name="Owner Test Organization",
        slug="owner-test-organization",
    )
    db_session.add(organization)
    db_session.flush()

    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=authenticated_user.id,
        role="owner",
        has_held_privileged_role=True,
        has_held_owner_role=True,
        is_active=True,
    )
    db_session.add(membership)
    db_session.commit()

    response = client.patch(
        f"/api/v1/organizations/{organization.id}",
        json={"name": "Updated by Owner"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated by Owner"


def test_update_organization_normalizes_slug(client):
    create_response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Original Organization",
            "slug": "original-organization",
        },
    )

    assert create_response.status_code == 201

    organization_id = create_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}",
        json={"slug": " Updated-Company "},
    )

    assert response.status_code == 200
    assert response.json()["slug"] == "updated-company"


def test_create_organization_rejects_whitespace_name(client):
    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "   ",
            "slug": "valid-organization",
        },
    )

    assert response.status_code == 422


def test_create_organization_rejects_whitespace_slug(client):
    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Valid Organization",
            "slug": "   ",
        },
    )

    assert response.status_code == 422


def test_create_organization_normalizes_name_and_slug(client):
    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "  Acme Corporation  ",
            "slug": "  ACME-CORPORATION  ",
        },
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Acme Corporation"
    assert response.json()["slug"] == "acme-corporation"


def test_update_organization_rejects_whitespace_name(client):
    create_response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Original Organization",
            "slug": "original-organization",
        },
    )

    organization_id = create_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}",
        json={"name": "   "},
    )

    assert response.status_code == 422

