import uuid

import pytest

from app.api.routes import invitations as invitation_routes
from app.models.invitation import OrganizationInvitation
from app.models.membership import OrganizationMembership
from app.models.user import User
from app.services import invitation_service


def _organization(client):
    unique = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/v1/organizations/",
        json={"name": f"Invite Org {unique}", "slug": f"invite-org-{unique}"},
    )
    assert response.status_code == 201
    return response.json()["id"]


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
    # Committed: a refused request rolls the session back.
    db_session.commit()
    return user


def _invite(client, organization_id, email="guest@example.com", role="member"):
    return client.post(
        f"/api/v1/organizations/{organization_id}/invitations/",
        json={"email": email, "role": role},
    )


def test_owner_invites_and_receives_a_one_time_token(client, db_session):
    organization_id = _organization(client)

    response = _invite(client, organization_id, email="Guest@Example.com")

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "guest@example.com"
    assert data["status"] == "pending"
    assert len(data["token"]) >= 40

    stored = db_session.get(OrganizationInvitation, uuid.UUID(data["id"]))
    assert stored.token_hash == invitation_service.hash_invitation_token(
        data["token"]
    )
    assert data["token"] not in stored.token_hash


def test_a_second_pending_invitation_for_the_same_email_is_refused(client):
    organization_id = _organization(client)

    assert _invite(client, organization_id).status_code == 201
    assert _invite(client, organization_id).status_code == 409


def test_admin_invites_members_but_not_admins(
    client,
    client_for_user,
    db_session,
):
    organization_id = _organization(client)
    admin = _member(db_session, organization_id, "admin")

    with client_for_user(admin) as admin_client:
        assert _invite(
            admin_client, organization_id, role="admin"
        ).status_code == 403
        assert _invite(
            admin_client, organization_id, role="member"
        ).status_code == 201


def test_members_cannot_manage_invitations(
    client,
    client_for_user,
    db_session,
):
    organization_id = _organization(client)
    member = _member(db_session, organization_id, "member")

    with client_for_user(member) as member_client:
        assert _invite(member_client, organization_id).status_code == 403
        assert member_client.get(
            f"/api/v1/organizations/{organization_id}/invitations/"
        ).status_code == 403


def test_list_shows_pending_invitations_without_tokens(client):
    organization_id = _organization(client)
    created = _invite(client, organization_id).json()

    response = client.get(
        f"/api/v1/organizations/{organization_id}/invitations/"
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [created["id"]]
    assert "token" not in response.json()[0]


def test_revoked_invitation_leaves_the_pending_list(client):
    organization_id = _organization(client)
    created = _invite(client, organization_id).json()
    base = f"/api/v1/organizations/{organization_id}/invitations"

    assert client.delete(f"{base}/{created['id']}").status_code == 204
    assert client.get(f"{base}/").json() == []
    assert client.delete(f"{base}/{created['id']}").status_code == 404


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (invitation_service.InvitationNotFoundError, 404),
        (invitation_service.InvitationEmailMismatchError, 403),
        (invitation_service.AlreadyMemberError, 409),
    ],
)
def test_accept_maps_refusals_to_http_errors(
    client,
    monkeypatch,
    error,
    status_code,
):
    def refuse(db, *, token):
        raise error("refused")

    monkeypatch.setattr(invitation_routes, "accept_invitation", refuse)

    response = client.post(
        "/api/v1/invitations/accept",
        json={"token": "x" * 43},
    )

    assert response.status_code == status_code
