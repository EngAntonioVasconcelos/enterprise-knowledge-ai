
import uuid
from unittest.mock import Mock

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.membership import OrganizationMembership
from app.models.user import User


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


def create_organization_user(client, organization_id, **overrides):
    payload = {
        "email": "employee@example.com",
        "full_name": "John Smith",
        **overrides,
    }

    response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json=payload,
    )

    return response


def test_create_user(client):
    organization_id = create_test_organization(client)

    response = create_organization_user(
        client,
        organization_id,
        email="employee@example.com",
    )

    assert response.status_code == 201

    data = response.json()

    assert data["email"] == "employee@example.com"
    assert data["full_name"] == "John Smith"
    assert data["is_active"] is True
    assert data["membership"]["organization_id"] == organization_id
    assert data["membership"]["role"] == "member"
    assert data["membership"]["is_active"] is True


def test_create_user_with_admin_role(client):
    organization_id = create_test_organization(client)

    response = create_organization_user(
        client,
        organization_id,
        email="admin@example.com",
        full_name="Organization Admin",
        role="admin",
    )

    assert response.status_code == 201
    assert response.json()["membership"]["role"] == "admin"


def test_create_user_with_nonexistent_organization(client):
    organization_id = uuid.uuid4()

    response = create_organization_user(client, organization_id)

    assert response.status_code == 404


def test_create_duplicate_user_membership(client):
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


def test_list_organization_users_includes_owner(client):
    organization_id = create_test_organization(client)

    response = client.get(
        f"/api/v1/organizations/{organization_id}/users/"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["membership"]["role"] == "owner"


def test_list_organization_users(client):
    organization_id = create_test_organization(client)

    for index in range(2):
        response = create_organization_user(
            client,
            organization_id,
            email=f"employee{index}@example.com",
            full_name=f"Employee {index}",
        )
        assert response.status_code == 201

    response = client.get(
        f"/api/v1/organizations/{organization_id}/users/"
    )

    assert response.status_code == 200
    assert len(response.json()) == 3

    roles = [item["membership"]["role"] for item in response.json()]
    assert roles.count("owner") == 1
    assert roles.count("member") == 2


def test_list_organization_users_with_pagination(client):
    organization_id = create_test_organization(client)

    for index in range(3):
        response = create_organization_user(
            client,
            organization_id,
            email=f"employee{index}@example.com",
            full_name=f"Employee {index}",
        )
        assert response.status_code == 201

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

    monkeypatch.setattr(db_session, "commit", raise_integrity_error)

    rollback_mock = Mock()
    monkeypatch.setattr(db_session, "rollback", rollback_mock)

    response = create_organization_user(client, organization_id)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "User could not be added because of a data conflict."
    }
    rollback_mock.assert_called_once()


def test_get_user(client):
    organization_id = create_test_organization(client)

    user_response = create_organization_user(
        client,
        organization_id,
        email="john@example.com",
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
    assert response.json()["membership"]["role"] == "member"


def test_get_nonexistent_user(client):
    organization_id = create_test_organization(client)
    user_id = uuid.uuid4()

    response = client.get(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found."


def test_update_user_membership_role(client):
    organization_id = create_test_organization(client)

    user_response = create_organization_user(
        client,
        organization_id,
        email="john@example.com",
    )
    user_id = user_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{user_id}/membership",
        json={"role": "admin"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["user_id"] == user_id
    assert response.json()["organization_id"] == organization_id


def test_update_user_membership_with_empty_payload(client):
    organization_id = create_test_organization(client)

    user_response = create_organization_user(client, organization_id)
    user_id = user_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{user_id}/membership",
        json={},
    )

    assert response.status_code == 422


def test_update_user_membership_with_invalid_role(client):
    organization_id = create_test_organization(client)

    user_response = create_organization_user(client, organization_id)
    user_id = user_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{user_id}/membership",
        json={"role": "superadmin"},
    )

    assert response.status_code == 422



def test_admin_cannot_create_another_admin(
    client,
    client_for_user,
    db_session,
):
    organization_id = create_test_organization(client)

    admin_response = create_organization_user(
        client,
        organization_id,
        email="admin@example.com",
        full_name="Organization Admin",
        role="admin",
    )

    assert admin_response.status_code == 201

    admin_user = db_session.get(
        User,
        uuid.UUID(admin_response.json()["id"]),
    )

    assert admin_user is not None

    with client_for_user(admin_user) as admin_client:
        response = admin_client.post(
            f"/api/v1/organizations/{organization_id}/users/",
            json={
                "email": "another-admin@example.com",
                "full_name": "Another Admin",
                "role": "admin",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == (
    "Insufficient organization permissions."
)


    # The authenticated test user is the organization Owner.
    # This test's current authentication fixture will be adjusted
    # when multi-user authentication test helpers are introduced.
    response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={
            "email": "another-owner@example.com",
            "full_name": "Another Owner",
            "role": "owner",
        },
    )

    assert response.status_code == 201


def test_deactivate_user_deactivates_membership_only(
    client,
    db_session,
):
    organization_id = create_test_organization(client)

    user_response = create_organization_user(
        client,
        organization_id,
        email="john@example.com",
    )
    user_id = uuid.UUID(user_response.json()["id"])

    response = client.delete(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    assert response.status_code == 204
    assert response.content == b""

    user = db_session.get(User, user_id)
    membership = db_session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == uuid.UUID(organization_id),
            OrganizationMembership.user_id == user_id,
        )
    )

    assert user is not None
    assert user.is_active is True
    assert membership is not None
    assert membership.is_active is False


def test_delete_already_deactivated_membership(client):
    organization_id = create_test_organization(client)

    user_response = create_organization_user(client, organization_id)
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

    response = client.delete(
        f"/api/v1/organizations/{organization_id}/users/{uuid.uuid4()}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found."


def test_delete_user_from_another_organization(client):
    first_organization_id = create_test_organization(client)
    second_organization_id = create_test_organization(client)

    user_response = create_organization_user(
        client,
        first_organization_id,
        email="john@example.com",
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


def test_deactivated_membership_is_excluded_from_list(client):
    organization_id = create_test_organization(client)

    user_response = create_organization_user(client, organization_id)
    user_id = user_response.json()["id"]

    client.delete(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    response = client.get(
        f"/api/v1/organizations/{organization_id}/users/"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["membership"]["role"] == "owner"


def test_deactivated_membership_cannot_be_retrieved(client):
    organization_id = create_test_organization(client)

    user_response = create_organization_user(client, organization_id)
    user_id = user_response.json()["id"]

    client.delete(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    response = client.get(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    assert response.status_code == 404


def test_deactivated_membership_cannot_be_updated(client):
    organization_id = create_test_organization(client)

    user_response = create_organization_user(client, organization_id)
    user_id = user_response.json()["id"]

    client.delete(
        f"/api/v1/organizations/{organization_id}/users/{user_id}"
    )

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{user_id}/membership",
        json={"role": "admin"},
    )

    assert response.status_code == 404


def test_update_membership_handles_integrity_error(
    client,
    db_session,
    monkeypatch,
):
    organization_id = create_test_organization(client)

    user_response = create_organization_user(
        client,
        organization_id,
        email="john@example.com",
    )
    user_id = user_response.json()["id"]

    def raise_integrity_error():
        raise IntegrityError(
            "UPDATE",
            {},
            Exception("Simulated integrity error"),
        )

    monkeypatch.setattr(db_session, "commit", raise_integrity_error)

    rollback_mock = Mock()
    monkeypatch.setattr(db_session, "rollback", rollback_mock)

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{user_id}/membership",
        json={"role": "admin"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Membership update conflicts with existing data."
    }
    rollback_mock.assert_called_once()

def test_admin_cannot_change_another_admin_membership(
    client,
    client_for_user,
    db_session,
):
    organization_id = create_test_organization(client)

    first_admin_response = create_organization_user(
        client,
        organization_id,
        email="first-admin@example.com",
        full_name="First Admin",
        role="admin",
    )
    assert first_admin_response.status_code == 201

    second_admin_response = create_organization_user(
        client,
        organization_id,
        email="second-admin@example.com",
        full_name="Second Admin",
        role="admin",
    )
    assert second_admin_response.status_code == 201

    first_admin = db_session.get(
        User,
        uuid.UUID(first_admin_response.json()["id"]),
    )

    second_admin_id = second_admin_response.json()["id"]

    with client_for_user(first_admin) as admin_client:
        response = admin_client.patch(
            f"/api/v1/organizations/{organization_id}/users/"
            f"{second_admin_id}/membership",
            json={"role": "member"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == (
    "Only an owner can manage owner or admin memberships."
)

def test_admin_cannot_remove_another_admin(
    client,
    client_for_user,
    db_session,
):
    organization_id = create_test_organization(client)

    first_admin_response = create_organization_user(
        client,
        organization_id,
        email="first-admin@example.com",
        full_name="First Admin",
        role="admin",
    )
    assert first_admin_response.status_code == 201

    second_admin_response = create_organization_user(
        client,
        organization_id,
        email="second-admin@example.com",
        full_name="Second Admin",
        role="admin",
    )
    assert second_admin_response.status_code == 201

    first_admin = db_session.get(
        User,
        uuid.UUID(first_admin_response.json()["id"]),
    )

    second_admin_id = second_admin_response.json()["id"]

    with client_for_user(first_admin) as admin_client:
        response = admin_client.delete(
            f"/api/v1/organizations/{organization_id}/users/"
            f"{second_admin_id}"
        )

    assert response.status_code == 403
    assert response.json()["detail"] == (
    "Only an owner can deactivate owner or admin memberships."
)
