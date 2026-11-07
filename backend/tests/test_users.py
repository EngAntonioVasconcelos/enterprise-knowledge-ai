
import uuid
from unittest.mock import Mock
from sqlalchemy.exc import IntegrityError

def create_test_organization(client):
    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Test Organization",
            "slug": "test-organization",
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


def test_create_user(client):
    organization_id = create_test_organization(client)

    response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "employee@example.com",
            "full_name": "John Smith",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["email"] == "employee@example.com"
    assert data["full_name"] == "John Smith"
    assert data["role"] == "member"
    assert data["is_active"] is True
    assert data["organization_id"] == organization_id


def test_create_user_with_admin_role(client):
    organization_id = create_test_organization(client)

    response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "admin@example.com",
            "full_name": "Organization Admin",
            "role": "admin",
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "admin"


def test_create_user_with_nonexistent_organization(client):
    organization_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "employee@example.com",
            "full_name": "John Smith",
        },
    )

    assert response.status_code == 404


def test_create_duplicate_user_email(client):
    organization_id = create_test_organization(client)

    payload = {
        "email": "employee@example.com",
        "full_name": "John Smith",
    }

    first_response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json=payload,
    )

    second_response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_list_organization_users_empty(client):
    organization_id = create_test_organization(client)

    response = client.get(
        f"/api/v1/organizations/{organization_id}/users/"
    )

    assert response.status_code == 200
    assert response.json() == []


def test_list_organization_users(client):
    organization_id = create_test_organization(client)

    for index in range(2):
        client.post(
            f"/api/v1/organizations/{organization_id}/users/",
            json={
                "email": f"employee{index}@example.com",
                "full_name": f"Employee {index}",
            },
        )

    response = client.get(
        f"/api/v1/organizations/{organization_id}/users/"
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_organization_users_with_pagination(client):
    organization_id = create_test_organization(client)

    for index in range(3):
        client.post(
            f"/api/v1/organizations/{organization_id}/users/",
            json={
                "email": f"employee{index}@example.com",
                "full_name": f"Employee {index}",
            },
        )

    response = client.get(
        f"/api/v1/organizations/{organization_id}/users/?skip=0&limit=2"
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_users_with_nonexistent_organization(client):
    organization_id = uuid.uuid4()

    response = client.get(
        f"/api/v1/organizations/{organization_id}/users/"
    )

    assert response.status_code == 404

def test_create_user_handles_integrity_error(
    client,
    db_session,
    monkeypatch,
):
    organization_id = create_test_organization(client)

    def raise_integrity_error():
        raise IntegrityError(
            "INSERT",
            {},
            Exception("Simulated integrity error"),
        )

    monkeypatch.setattr(
        db_session,
        "commit",
        raise_integrity_error,
    )

    rollback_mock = Mock()
    monkeypatch.setattr(
        db_session,
        "rollback",
        rollback_mock,
    )

    response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "employee@example.com",
            "full_name": "John Smith",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "User could not be created because of a data conflict."
    }
    rollback_mock.assert_called_once()
def test_get_user(client):
    organization_id = create_test_organization(client)

    user_response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "john@example.com",
            "full_name": "John Smith",
            "role": "member",
        },
    )

    assert user_response.status_code == 201

    user_id = user_response.json()["id"]

    response = client.get(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == user_id
    assert response.json()["email"] == "john@example.com"
    assert response.json()["full_name"] == "John Smith"
    assert response.json()["role"] == "member"

def test_get_nonexistent_user(client):
    organization_id = create_test_organization(client)
    user_id = str(uuid.uuid4())

    response = client.get(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found."