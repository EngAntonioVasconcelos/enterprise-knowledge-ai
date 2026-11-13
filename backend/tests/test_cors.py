
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_cors_allows_configured_origin():
    response = client.options(
        "/api/v1/organizations/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "http://localhost:3000"
    )
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_rejects_unconfigured_origin():
    response = client.options(
        "/api/v1/organizations/",
        headers={
            "Origin": "https://untrusted.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
