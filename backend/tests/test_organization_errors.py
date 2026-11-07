
from sqlalchemy.exc import IntegrityError


def test_create_organization_handles_integrity_error(
    client,
    db_session,
    monkeypatch,
):
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

    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Test Organization",
            "slug": "test-organization",
        },
    )

    assert response.status_code == 409

    assert response.json() == {
        "detail": "Organization slug already exists."
    }

def test_update_organization_handles_integrity_error(
    client,
    db_session,
    monkeypatch,
):
    # Create an organization before simulating the database error.
    create_response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Test Organization",
            "slug": "test-organization",
        },
    )

    assert create_response.status_code == 201

    organization_id = create_response.json()["id"]

    # Simulate a database integrity error during the update.
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

    # Track whether the database rollback is executed.
    rollback_calls = []
    original_rollback = db_session.rollback

    def track_rollback():
        rollback_calls.append(True)
        original_rollback()

    monkeypatch.setattr(
        db_session,
        "rollback",
        track_rollback,
    )

    # Attempt to update the organization.
    response = client.patch(
        f"/api/v1/organizations/{organization_id}",
        json={"name": "Updated Organization"},
    )

    # Verify the API response and transaction rollback.
    assert response.status_code == 409
    assert response.json() == {
        "detail": "Organization update conflicts with existing data."
    }
    assert len(rollback_calls) == 1
