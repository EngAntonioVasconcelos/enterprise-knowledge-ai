
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
  

