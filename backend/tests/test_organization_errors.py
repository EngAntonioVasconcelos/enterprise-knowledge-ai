from sqlalchemy.exc import IntegrityError


def test_create_organization_handles_unexpected_integrity_error(
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

    assert response.status_code == 500
    assert response.json() == {
        "detail": "An unexpected database error occurred."
    }


def test_update_organization_handles_unexpected_integrity_error(
    client,
    db_session,
    monkeypatch,
):
    create_response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Test Organization",
            "slug": "test-organization",
        },
    )

    assert create_response.status_code == 201

    organization_id = create_response.json()["id"]

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

    response = client.patch(
        f"/api/v1/organizations/{organization_id}",
        json={"name": "Updated Organization"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "An unexpected database error occurred."
    }
    assert len(rollback_calls) == 1


def test_create_organization_returns_conflict_for_duplicate_slug(client):
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
