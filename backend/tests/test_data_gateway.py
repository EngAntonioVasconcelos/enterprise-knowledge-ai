import datetime as dt
import decimal
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.connectors import postgresql
from app.core.config import settings
from app.services import data_gateway, data_tool
from app.services.tabular_engine import QueryResult


ORG = uuid.uuid4()
TOKEN = "test-gateway-token"


def _connection(**changes):
    values = dict(
        id=uuid.uuid4(),
        organization_id=ORG,
        name="Vendas",
        provider="postgresql",
        status="active",
        disconnected_at=None,
        catalog={"tables": []},
        settings={"host": "db.example.com", "database": "sales"},
    )
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.fixture
def gateway(monkeypatch):
    connections = [
        _connection(name="Vendas"),
        _connection(name="RH", settings={"scope": {"roles": ["owner", "admin"]}}),
        _connection(name="Drive", provider="google_drive"),
        _connection(name="Parada", status="error"),
    ]
    monkeypatch.setattr(settings, "DATA_GATEWAY_TOKEN", TOKEN)
    monkeypatch.setattr(data_gateway, "_connections", lambda db, organization_id: connections)
    data_gateway.app.dependency_overrides[data_gateway.get_session] = lambda: None
    client = TestClient(data_gateway.app)
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    yield client, connections
    data_gateway.app.dependency_overrides.clear()


def test_a_role_sees_only_the_connections_it_may_use(gateway):
    client, _ = gateway
    names = lambda role: [  # noqa: E731
        item["name"]
        for item in client.post(
            "/v1/connections", json={"organization_id": str(ORG), "role": role}
        ).json()["connections"]
    ]
    assert names("member") == ["Vendas"]
    assert names("admin") == ["Vendas", "RH"]


def test_every_call_needs_the_token(gateway, monkeypatch):
    client, _ = gateway
    body = {"organization_id": str(ORG), "role": "owner"}
    assert client.post("/v1/connections", json=body, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/v1/connections", json=body, headers={"Authorization": ""}).status_code == 401
    monkeypatch.setattr(settings, "DATA_GATEWAY_TOKEN", None)
    assert client.post("/v1/connections", json=body).status_code == 503


def test_a_query_runs_read_only_with_the_agent_limits(gateway, monkeypatch):
    client, connections = gateway
    seen = {}
    monkeypatch.setattr(data_gateway, "load_credentials", lambda db, **kw: {"username": "u", "password": "p"})

    def run(target, sql, *, max_rows, statement_timeout_ms):
        seen.update(sql=sql, max_rows=max_rows, timeout=statement_timeout_ms, host=target.host)
        return QueryResult(
            ("customer", "total", "day"),
            (("Ana", decimal.Decimal("15.75"), dt.date(2026, 11, 2)),),
            False,
        )

    monkeypatch.setattr(postgresql, "run_read_only_query", run)
    monkeypatch.setattr(postgresql, "checked_address", lambda target: "203.0.113.5")
    response = client.post(
        "/v1/query",
        json={
            "organization_id": str(ORG),
            "role": "member",
            "connection_id": str(connections[0].id),
            "sql": "SELECT customer, sum(amount) AS total FROM public.orders GROUP BY 1",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "columns": ["customer", "total", "day"],
        "rows": [["Ana", "15.75", "2026-11-02"]],
        "truncated": False,
    }
    assert (seen["max_rows"], seen["timeout"]) == (settings.DATA_QUERY_MAX_ROWS, settings.DATA_QUERY_TIMEOUT_MS)


@pytest.mark.parametrize("index, role", [(1, "member"), (2, "owner"), (3, "owner")])
def test_a_query_on_a_connection_the_role_may_not_use_is_refused(gateway, index, role):
    client, connections = gateway
    response = client.post(
        "/v1/query",
        json={
            "organization_id": str(ORG),
            "role": role,
            "connection_id": str(connections[index].id),
            "sql": "SELECT 1",
        },
    )
    assert response.status_code == 404


def test_a_refused_query_is_a_422_without_the_query_in_the_log(gateway, monkeypatch, caplog):
    client, connections = gateway
    monkeypatch.setattr(data_gateway, "load_credentials", lambda db, **kw: {"username": "u", "password": "p"})

    def refuse(*args, **kwargs):
        raise postgresql.DatabaseQueryError("The query failed: syntax error")

    monkeypatch.setattr(postgresql, "run_read_only_query", refuse)
    response = client.post(
        "/v1/query",
        json={
            "organization_id": str(ORG),
            "role": "member",
            "connection_id": str(connections[0].id),
            "sql": "DELETE FROM secret_table",
        },
    )
    assert response.status_code == 422
    assert "secret_table" not in caplog.text


def test_unknown_fields_and_roles_are_refused(gateway):
    client, _ = gateway
    assert client.post("/v1/connections", json={"organization_id": str(ORG), "role": "root"}).status_code == 422
    assert (
        client.post(
            "/v1/connections", json={"organization_id": str(ORG), "role": "owner", "x": 1}
        ).status_code
        == 422
    )


def test_no_gateway_configured_means_no_data_tool(monkeypatch):
    monkeypatch.setattr(settings, "DATA_GATEWAY_URL", None)
    assert data_tool.data_tool_for(organization_id=ORG, role="member") is None
    monkeypatch.setattr(settings, "DATA_GATEWAY_URL", "http://data-gateway:8100")
    monkeypatch.setattr(settings, "DATA_GATEWAY_TOKEN", "t")
    assert data_tool.data_tool_for(organization_id=ORG, role="member") is not None


def test_an_unreachable_gateway_leaves_the_documents(monkeypatch):
    monkeypatch.setattr(settings, "DATA_GATEWAY_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(settings, "DATA_GATEWAY_TOKEN", "t")
    tool = data_tool.data_tool_for(organization_id=ORG, role="member")
    assert tool.connections() == []
    with pytest.raises(data_tool.DataToolError):
        tool.query(uuid.uuid4(), "SELECT 1")
