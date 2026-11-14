
import uuid
from unittest.mock import Mock

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.main import app
from app.models.membership import OrganizationMembership
from app.models.user import User
from app.schemas.membership import OrganizationUserResponse


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


class _Added:
    """Result of adding a member in test setup, shaped like the API response."""

    status_code = 201

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def add_member(client, organization_id, **overrides):
    """Add a member directly in the test database.

    Members join through invitations, which are accepted by a PostgreSQL
    function (tests/integration/test_invitations_rls.py). These SQLite tests
    only need someone in the organization to act on.
    """
    db = next(app.dependency_overrides[get_db]())
    email = overrides.get("email", "employee@example.com")
    role = overrides.get("role", "member")

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            full_name=overrides.get("full_name", "John Smith"),
            is_active=True,
        )
        db.add(user)
        db.flush()

    membership = OrganizationMembership(
        organization_id=uuid.UUID(str(organization_id)),
        user_id=user.id,
        role=role,
        is_active=True,
        has_held_privileged_role=role in {"owner", "admin"},
        has_held_owner_role=role == "owner",
    )
    db.add(membership)
    db.commit()

    return _Added(
        OrganizationUserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
            membership=membership,
        ).model_dump(mode="json")
    )


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
        response = add_member(
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
        response = add_member(
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


def test_get_user(client):
    organization_id = create_test_organization(client)

    user_response = add_member(
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

    user_response = add_member(
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

    user_response = add_member(client, organization_id)
    user_id = user_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{user_id}/membership",
        json={},
    )

    assert response.status_code == 422


def test_update_user_membership_with_invalid_role(client):
    organization_id = create_test_organization(client)

    user_response = add_member(client, organization_id)
    user_id = user_response.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{organization_id}/users/{user_id}/membership",
        json={"role": "superadmin"},
    )

    assert response.status_code == 422



def test_deactivate_user_deactivates_membership_only(
    client,
    db_session,
):
    organization_id = create_test_organization(client)

    user_response = add_member(
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

    user_response = add_member(client, organization_id)
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

    user_response = add_member(
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

    user_response = add_member(client, organization_id)
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

    user_response = add_member(client, organization_id)
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

    user_response = add_member(client, organization_id)
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

    user_response = add_member(
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

    first_admin_response = add_member(
        client,
        organization_id,
        email="first-admin@example.com",
        full_name="First Admin",
        role="admin",
    )
    assert first_admin_response.status_code == 201

    second_admin_response = add_member(
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

    first_admin_response = add_member(
        client,
        organization_id,
        email="first-admin@example.com",
        full_name="First Admin",
        role="admin",
    )
    assert first_admin_response.status_code == 201

    second_admin_response = add_member(
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


def test_members_cannot_be_added_without_an_invitation(client):
    organization_id = create_test_organization(client)

    response = client.post(
        f"/api/v1/organizations/{organization_id}/users/",
        json={"email": "employee@example.com", "full_name": "John Smith"},
    )

    assert response.status_code == 405
