import uuid

import pytest

from app.api.routes import directory as directory_routes
from app.models.membership import OrganizationMembership
from app.models.user import User


def _organization(client):
    unique = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/v1/organizations/",
        json={"name": f"Directory Org {unique}", "slug": f"dir-org-{unique}"},
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
    db_session.commit()
    return user


@pytest.fixture
def fake_directory(monkeypatch):
    # The directory is a PostgreSQL function (tested in
    # tests/integration/test_directory_rls.py); SQLite has no equivalent.
    def directory(db, *, organization_id, skip, limit):
        return [
            {"user_id": uuid.uuid4(), "full_name": "Ana Lima", "role": "owner"}
        ]

    monkeypatch.setattr(directory_routes, "list_directory", directory)


def test_members_see_colleagues_without_emails(
    client,
    client_for_user,
    db_session,
    fake_directory,
):
    organization_id = _organization(client)
    member = _member(db_session, organization_id, "member")

    with client_for_user(member) as member_client:
        response = member_client.get(
            f"/api/v1/organizations/{organization_id}/directory/"
        )

    assert response.status_code == 200
    assert set(response.json()[0]) == {"user_id", "full_name", "role"}


@pytest.mark.parametrize("path", ["directory/", "users/"])
def test_viewers_see_neither_the_directory_nor_the_user_list(
    client,
    client_for_user,
    db_session,
    fake_directory,
    path,
):
    organization_id = _organization(client)
    viewer = _member(db_session, organization_id, "viewer")

    with client_for_user(viewer) as viewer_client:
        response = viewer_client.get(
            f"/api/v1/organizations/{organization_id}/{path}"
        )

    assert response.status_code == 403


def test_members_cannot_read_emails_through_the_user_routes(
    client,
    client_for_user,
    db_session,
):
    organization_id = _organization(client)
    member = _member(db_session, organization_id, "member")
    base = f"/api/v1/organizations/{organization_id}/users"

    with client_for_user(member) as member_client:
        assert member_client.get(f"{base}/").status_code == 403
        assert member_client.get(f"{base}/{member.id}").status_code == 403
