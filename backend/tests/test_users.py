
import uuid
from unittest.mock import Mock
from sqlalchemy.exc import IntegrityError


def create_test_organization(client):
    unique_id = uuid.uuid4().hex[:8]

    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": f"Test Organization {unique_id}",
            "slug": f"test-organization-{unique_id}",
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

def test_update_user_full_name(client):
    organization_id = create_test_organization(client)

    user_response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "john@example.com",
            "full_name": "John Smith",
            "role": "member",
        },
    )

    user_id = user_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{user_id}",
        json={"full_name": "John Updated"},
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "John Updated"
    assert response.json()["role"] == "member"


def test_update_user_role(client):
    organization_id = create_test_organization(client)

    user_response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "john@example.com",
            "full_name": "John Smith",
        },
    )

    user_id = user_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{user_id}",
        json={"role": "admin"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_deactivate_user(client):
    organization_id = create_test_organization(client)

    user_response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "john@example.com",
            "full_name": "John Smith",
        },
    )

    user_id = user_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{user_id}",
        json={"is_active": False},
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_update_user_with_empty_payload(client):
    organization_id = create_test_organization(client)

    user_response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "john@example.com",
            "full_name": "John Smith",
        },
    )

    user_id = user_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{user_id}",
        json={},
    )

    assert response.status_code == 422


def test_update_user_with_null_field(client):
    organization_id = create_test_organization(client)

    user_response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "john@example.com",
            "full_name": "John Smith",
        },
    )

    user_id = user_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{user_id}",
        json={"full_name": None},
    )

    assert response.status_code == 422


def test_update_user_with_invalid_role(client):
    organization_id = create_test_organization(client)

    user_response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "john@example.com",
            "full_name": "John Smith",
        },
    )

    user_id = user_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{user_id}",
        json={"role": "superadmin"},
    )

    assert response.status_code == 422

def test_update_nonexistent_user(client):
    organization_id = create_test_organization(client)

    nonexistent_user_id = "00000000-0000-0000-0000-000000000001"

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{nonexistent_user_id}",
        json={"full_name": "Updated Name"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found."


def test_update_user_from_another_organization(client):
    first_organization_id = create_test_organization(client)
    second_organization_id = create_test_organization(client)

    user_response = client.post(
        f"/api/v1/organizations/{first_organization_id}/users/",
        json={
            "email": "john@example.com",
            "full_name": "John Smith",
        },
    )

    user_id = user_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{second_organization_id}/users/{user_id}",
        json={"full_name": "Unauthorized Update"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found."

    original_user = client.get(
        f"/api/v1/organizations/{first_organization_id}/users/{user_id}"
    )

    assert original_user.status_code == 200
    assert original_user.json()["full_name"] == "John Smith"

def test_delete_user(client):
    organization_id = create_test_organization(client)

    user_response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "john@example.com",
            "full_name": "John Smith",
        },
    )

    user_id = user_response.json()["id"]

    response = client.delete(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    assert response.status_code == 204
    assert response.content == b""


def test_delete_already_deactivated_user(client):
    organization_id = create_test_organization(client)

    user_response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "john@example.com",
            "full_name": "John Smith",
        },
    )

    user_id = user_response.json()["id"]

    first_response = client.delete(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    second_response = client.delete(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    assert first_response.status_code == 204
    assert second_response.status_code == 204


def test_delete_nonexistent_user(client):
    organization_id = create_test_organization(client)
    user_id = uuid.uuid4()

    response = client.delete(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found."


def test_delete_user_from_another_organization(client):
    first_organization_id = create_test_organization(client)
    second_organization_id = create_test_organization(client)

    user_response = client.post(
        f"/api/v1/organizations/{first_organization_id}/users/",
        json={
            "email": "john@example.com",
            "full_name": "John Smith",
        },
    )

    user_id = user_response.json()["id"]

    response = client.delete(
        f"/api/v1/organizations/{second_organization_id}/users/{user_id}"
    )

    assert response.status_code == 404

    original_user = client.get(
        f"/api/v1/organizations/{first_organization_id}/users/{user_id}"
    )

    assert original_user.status_code == 200
    assert original_user.json()["is_active"] is True


def test_deactivated_user_is_excluded_from_list(client):
    organization_id = create_test_organization(client)

    user_response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "john@example.com",
            "full_name": "John Smith",
        },
    )

    user_id = user_response.json()["id"]

    client.delete(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    response = client.get(
        f"/api/v1/organizations/{organization_id}/users/"
    )

    assert response.status_code == 200
    assert response.json() == []


def test_deactivated_user_cannot_be_retrieved(client):
    organization_id = create_test_organization(client)

    user_response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "john@example.com",
            "full_name": "John Smith",
        },
    )

    user_id = user_response.json()["id"]

    client.delete(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    response = client.get(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    assert response.status_code == 404


def test_deactivated_user_cannot_be_updated(client):
    organization_id = create_test_organization(client)

    user_response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "john@example.com",
            "full_name": "John Smith",
        },
    )

    user_id = user_response.json()["id"]

    client.delete(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{user_id}",
        json={"full_name": "Updated Name"},
    )

    assert response.status_code == 404

def test_update_user_handles_integrity_error(
    client,
    db_session,
    monkeypatch,
):
    organization_id = create_test_organization(client)

    user_response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "john@example.com",
            "full_name": "John Smith",
        },
    )

    user_id = user_response.json()["id"]

    def raise_integrity_error():
        raise IntegrityError(
            "UPDATE",
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

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{user_id}",
        json={"full_name": "Updated Name"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "User update conflicts with existing data."
    }

    rollback_mock.assert_called_once()
