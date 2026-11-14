import uuid

from app.models.membership import OrganizationMembership
from app.models.user import User


def _organization(client):
    unique = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/v1/organizations/",
        json={"name": f"Sources Org {unique}", "slug": f"sources-{unique}"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _base(organization_id):
    return f"/api/v1/organizations/{organization_id}/connections"


def _create(client, organization_id, **values):
    body = {"provider": "google_drive", "name": "Company Drive"}
    body.update(values)
    return client.post(f"{_base(organization_id)}/", json=body)


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


def test_an_owner_connects_a_source_and_the_kind_follows_the_provider(
    client,
):
    organization_id = _organization(client)

    response = _create(
        client,
        organization_id,
        name="  Company   Drive ",
        settings={"folder_ids": ["abc"]},
    )

    assert response.status_code == 201
    data = response.json()
    assert (data["provider"], data["kind"]) == ("google_drive", "documents")
    assert (data["name"], data["status"]) == ("Company Drive", "active")
    assert data["settings"] == {"folder_ids": ["abc"]}
    assert data["disconnected_at"] is None

    spreadsheet = _create(
        client, organization_id, provider="spreadsheet_upload", name="Sales"
    )
    assert spreadsheet.json()["kind"] == "tabular"


def test_unknown_providers_are_refused(client):
    organization_id = _organization(client)

    response = _create(client, organization_id, provider="carrier_pigeon")

    assert response.status_code == 400
    assert "google_drive" in response.json()["detail"]


def test_credentials_never_go_into_settings(client):
    organization_id = _organization(client)

    for settings in (
        {"password": "x"},
        {"database": {"Api-Key": "x"}},
        {"accounts": [{"refresh_token": "x"}]},
    ):
        response = _create(client, organization_id, settings=settings)
        assert response.status_code == 422, settings
        assert "credentials" in response.text


def test_names_are_unique_among_connections_in_use(client):
    organization_id = _organization(client)
    first = _create(client, organization_id).json()

    assert _create(client, organization_id).status_code == 409

    disconnected = client.post(
        f"{_base(organization_id)}/{first['id']}/disconnect"
    )
    assert disconnected.status_code == 200
    assert _create(client, organization_id).status_code == 201


def test_admins_rename_pause_and_resume(client):
    organization_id = _organization(client)
    connection = _create(client, organization_id).json()
    url = f"{_base(organization_id)}/{connection['id']}"

    paused = client.patch(url, json={"status": "paused", "name": "Old Drive"})
    assert paused.status_code == 200
    assert (paused.json()["status"], paused.json()["name"]) == (
        "paused",
        "Old Drive",
    )

    resumed = client.patch(url, json={"status": "active"})
    assert resumed.json()["status"] == "active"

    # Disconnecting is final and has its own route.
    assert client.patch(url, json={"status": "disconnected"}).status_code == 422


def test_a_disconnected_connection_is_final_and_hidden_by_default(client):
    organization_id = _organization(client)
    connection = _create(client, organization_id).json()
    url = f"{_base(organization_id)}/{connection['id']}"

    disconnected = client.post(f"{url}/disconnect").json()
    assert disconnected["status"] == "disconnected"
    assert disconnected["disconnected_at"] is not None

    assert client.patch(url, json={"name": "Again"}).status_code == 409
    assert client.post(f"{url}/disconnect").status_code == 409

    listed = client.get(f"{_base(organization_id)}/").json()
    assert listed == []
    everything = client.get(
        f"{_base(organization_id)}/", params={"include_disconnected": True}
    ).json()
    assert [c["id"] for c in everything] == [connection["id"]]


def test_unknown_connections_are_not_found(client):
    organization_id = _organization(client)
    url = f"{_base(organization_id)}/{uuid.uuid4()}"

    assert client.get(url).status_code == 404
    assert client.patch(url, json={"name": "x"}).status_code == 404


def test_members_and_viewers_cannot_manage_connections(
    client,
    client_for_user,
    db_session,
):
    organization_id = _organization(client)

    for role in ("member", "viewer"):
        user = _member(db_session, organization_id, role)
        with client_for_user(user) as other:
            assert other.get(f"{_base(organization_id)}/").status_code == 403
            assert _create(other, organization_id).status_code == 403
