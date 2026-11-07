
import uuid


def test_create_organization(client):
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

    uuid.UUID(data["id"])

    assert "created_at" in data


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

