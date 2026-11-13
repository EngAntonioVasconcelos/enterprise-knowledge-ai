
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.main import app

from sqlalchemy.exc import SQLAlchemyError

client = TestClient(app)


def test_liveness_endpoint():
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "alive",
        "service": "enterprise-knowledge-ai-api",
    }


def test_readiness_endpoint_when_database_is_available(monkeypatch):
    mock_connection = Mock()

    class MockConnectionContext:
        def __enter__(self):
            return mock_connection

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    mock_engine = Mock()
    mock_engine.connect.return_value = MockConnectionContext()

    monkeypatch.setattr(
        "app.main.engine",
        mock_engine,
    )

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "enterprise-knowledge-ai-api",
        "database": "available",
    }


def test_readiness_endpoint_when_database_is_unavailable(monkeypatch):
    mock_engine = Mock()
    mock_engine.connect.side_effect = SQLAlchemyError("Database unavailable")

    monkeypatch.setattr(
        "app.main.engine",
        mock_engine,
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "service": "enterprise-knowledge-ai-api",
        "database": "unavailable",
    }
