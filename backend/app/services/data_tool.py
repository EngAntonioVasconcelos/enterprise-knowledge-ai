"""The agent's data tool (AL-4): read-only questions to a customer's database.

The API cannot open database credentials (ADR-007): only the data gateway
(app/services/data_gateway.py, a separate internal process with the
master private key) connects to customer databases. This module is the
API side: it asks the gateway which connections the person may use and
sends the model's SELECT to it.

What the model sees of a database is its catalog (table and column names,
types and comments), never its rows, until a query ran. Rows and catalog
text are customer data: they are passed to the model between tags and can
never close them, and they are never logged or kept.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings


logger = logging.getLogger("eka.data")

TOOL = "query_data"
MAX_CATALOG_CHARS = 8000
MAX_TABLE_COLUMNS = 40
MAX_CELL_CHARS = 200
MAX_DATA_CHARS = 6000


class DataToolError(RuntimeError):
    """The query was refused, failed or the gateway is unreachable."""


@dataclass(frozen=True)
class DataConnectionInfo:
    connection_id: uuid.UUID
    name: str
    catalog: dict


@dataclass(frozen=True)
class DataResult:
    columns: tuple[str, ...]
    rows: tuple[tuple, ...]
    truncated: bool


class DataTool(Protocol):
    def connections(self) -> list[DataConnectionInfo]: ...

    def query(self, connection_id: uuid.UUID, sql: str) -> DataResult: ...


def _clean(value) -> str:
    """Customer text cannot open or close a tag, or fill a placeholder."""
    text = "" if value is None else str(value)
    text = text.replace("<", "\u2039").replace(">", "\u203a").replace("{{", "{ {")
    return " ".join(text.split())


def render_catalog(connections: list[DataConnectionInfo]) -> str:
    """The databases the person may query, numbered, as the model reads them."""
    parts, used = [], 0
    for number, connection in enumerate(connections, start=1):
        lines = [f'<database id="{number}" name="{_clean(connection.name)[:100]}">']
        for table in (connection.catalog or {}).get("tables", []):
            columns = ", ".join(
                f"{_clean(column.get('name'))} {_clean(column.get('type'))}"
                for column in table.get("columns", [])[:MAX_TABLE_COLUMNS]
            )
            comment = _clean(table.get("comment"))[:150]
            line = f"{_clean(table.get('schema'))}.{_clean(table.get('name'))}({columns})"
            lines.append(line + (f" -- {comment}" if comment else ""))
        lines.append("</database>")
        block = "\n".join(lines)
        if parts and used + len(block) > MAX_CATALOG_CHARS:
            break
        parts.append(block[:MAX_CATALOG_CHARS])
        used += len(block)
    return "\n".join(parts)


def render_rows(name: str, result: DataResult) -> str:
    """The query result as the model reads it: one tagged table, cut short."""
    lines = [" | ".join(_clean(column)[:60] for column in result.columns)]
    used = len(lines[0])
    for row in result.rows:
        line = " | ".join(_clean(value)[:MAX_CELL_CHARS] for value in row)
        if used + len(line) > MAX_DATA_CHARS:
            break
        lines.append(line)
        used += len(line)
    shown = len(lines) - 1
    more = result.truncated or shown < len(result.rows)
    note = "\n(more rows exist; only these were read)" if more else ""
    return f'<data id="D1" database="{_clean(name)[:100]}">\n' + "\n".join(lines) + note + "\n</data>"


def data_text(result: DataResult) -> str:
    """Every value of the result, for the number check."""
    return " ".join(str(value) for row in result.rows for value in row if value is not None)


class GatewayDataTool:
    """The data tool through the internal data gateway, for one person."""

    def __init__(self, *, organization_id: uuid.UUID, role: str):
        self.organization_id = organization_id
        self.role = role
        self._client = httpx.Client(
            base_url=settings.DATA_GATEWAY_URL or "",
            timeout=settings.DATA_QUERY_TIMEOUT_MS / 1000 + 5,
            headers={"Authorization": f"Bearer {settings.DATA_GATEWAY_TOKEN or ''}"},
        )

    def _post(self, path: str, body: dict) -> dict:
        try:
            response = self._client.post(path, json=body)
        except httpx.HTTPError as exc:
            raise DataToolError(f"data gateway unreachable: {type(exc).__name__}") from None
        if response.status_code != 200:
            try:
                detail = str(response.json().get("detail", ""))[:300]
            except ValueError:
                detail = ""
            raise DataToolError(f"data gateway {response.status_code}: {detail}")
        return response.json()

    def connections(self) -> list[DataConnectionInfo]:
        try:
            body = self._post(
                "/v1/connections",
                {"organization_id": str(self.organization_id), "role": self.role},
            )
        except DataToolError as exc:
            # No data tool for this answer; documents still work.
            logger.warning("data connections unavailable: %s", exc)
            return []
        return [
            DataConnectionInfo(uuid.UUID(item["connection_id"]), item["name"], item["catalog"])
            for item in body.get("connections", [])
        ]

    def query(self, connection_id: uuid.UUID, sql: str) -> DataResult:
        body = self._post(
            "/v1/query",
            {
                "organization_id": str(self.organization_id),
                "role": self.role,
                "connection_id": str(connection_id),
                "sql": sql,
            },
        )
        return DataResult(
            columns=tuple(body["columns"]),
            rows=tuple(tuple(row) for row in body["rows"]),
            truncated=bool(body["truncated"]),
        )


def data_tool_for(*, organization_id: uuid.UUID, role: str) -> DataTool | None:
    """The data tool, or None when no gateway is configured."""
    if not settings.DATA_GATEWAY_URL or not settings.DATA_GATEWAY_TOKEN:
        return None
    return GatewayDataTool(organization_id=organization_id, role=role)
