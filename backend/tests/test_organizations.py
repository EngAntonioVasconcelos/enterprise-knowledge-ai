
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

