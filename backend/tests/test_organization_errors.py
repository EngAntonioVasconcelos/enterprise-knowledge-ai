
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
