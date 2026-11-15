"""Read-only access to a customer's PostgreSQL database (ADR-006).

A database is not copied into the platform: its schema is described
(the catalog, so the agent knows what it can ask) and questions run live,
read-only. Credentials are sealed (ADR-007), so only the worker side can
connect.

Defences, each enough on its own for its threat, all applied together:

- Address: the host is resolved once and every address must be public
  (no loopback, private or link-local networks, so a connection cannot be
  pointed at our own infrastructure); the connection then goes to that
  checked address. Development can allow private addresses with
  DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS. The platform's own databases
  are refused always.
- Read only: every session starts read-only, and every query runs in a
  READ ONLY transaction that is rolled back.
- One SELECT: the query is wrapped as a sub-query (anything but a SELECT
  is a syntax error there, and data-modifying WITH is refused by
  PostgreSQL) and sent as a prepared statement, which refuses a second
  statement smuggled in.
- Limits: statement timeout, connect timeout, maximum rows, long values
  cut.

The customer should still give a role with SELECT only: this is defence in
depth, not a replacement for least privilege.
"""

import ipaddress
import socket
from dataclasses import dataclass

import psycopg
from sqlalchemy.engine import make_url

from app.connectors.base import ConnectorError
from app.core.config import settings
from app.core.errors import InvalidInputError
from app.services.tabular_engine import QueryResult


SSL_MODES = ("require", "verify-ca", "verify-full", "disable")
SETTING_KEYS = ("host", "port", "database", "sslmode", "schemas", "scope")

CONNECT_TIMEOUT_SECONDS = 10
STATEMENT_TIMEOUT_MS = 15_000
MAX_ROWS = 1000
MAX_VALUE_CHARS = 2000
MAX_TABLES = 500
MAX_COLUMNS = 200


class DatabaseConnectorError(ConnectorError):
    """The database could not be reached or refused the session."""


class DatabaseQueryError(InvalidInputError):
    """The question's query was refused or failed."""


class UnsafeHostError(InvalidInputError):
    pass


@dataclass(frozen=True)
class DatabaseTarget:
    host: str
    port: int
    database: str
    sslmode: str
    schemas: tuple[str, ...]
    username: str
    password: str

    def __repr__(self) -> str:
        return (
            f"DatabaseTarget({self.host}:{self.port}/{self.database}, "
            "credentials=<hidden>)"
        )


def validate_settings(value: dict) -> dict:
    """Settings of a postgresql connection; raises InvalidInputError."""
    unknown = set(value) - set(SETTING_KEYS)
    if unknown:
        raise InvalidInputError(
            f"Unknown settings for PostgreSQL: {', '.join(sorted(unknown))}"
        )
    host = value.get("host")
    if not isinstance(host, str) or not host.strip() or len(host) > 253:
        raise InvalidInputError("host is required")
    if any(ch in host for ch in " /\\=?'\""):
        raise InvalidInputError("host must be a host name or an IP address")
    port = value.get("port", 5432)
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise InvalidInputError("port must be a number from 1 to 65535")
    database = value.get("database")
    if not isinstance(database, str) or not database.strip() or len(database) > 63:
        raise InvalidInputError("database is required")
    sslmode = value.get("sslmode", "require")
    if sslmode not in SSL_MODES:
        raise InvalidInputError(f"sslmode must be one of: {', '.join(SSL_MODES)}")
    if sslmode == "disable" and not settings.DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS:
        # Without TLS the password would cross the network in clear.
        raise InvalidInputError("sslmode disable is allowed only in development")
    schemas = value.get("schemas", ["public"])
    if (
        not isinstance(schemas, list)
        or not schemas
        or len(schemas) > 50
        or any(not isinstance(s, str) or not s or len(s) > 63 for s in schemas)
    ):
        raise InvalidInputError("schemas must be a list of schema names")
    return value


def build_target(connection_settings: dict, credentials: dict | None) -> DatabaseTarget:
    validate_settings(connection_settings)
    credentials = credentials or {}
    username, password = credentials.get("username"), credentials.get("password")
    if not username or not password:
        raise DatabaseConnectorError(
            "this connection has no database credentials (username and password)"
        )
    return DatabaseTarget(
        host=connection_settings["host"].strip(),
        port=connection_settings.get("port", 5432),
        database=connection_settings["database"].strip(),
        sslmode=connection_settings.get("sslmode", "require"),
        schemas=tuple(connection_settings.get("schemas", ["public"])),
        username=username,
        password=password,
    )


def _platform_endpoints() -> set[tuple[str, int, str]]:
    endpoints = set()
    for url in (
        settings.DATABASE_URL,
        settings.MIGRATION_DATABASE_URL,
        settings.WORKER_DATABASE_URL,
        settings.MAILER_DATABASE_URL,
    ):
        if not url:
            continue
        parsed = make_url(url)
        endpoints.add(
            ((parsed.host or "").lower(), parsed.port or 5432, parsed.database or "")
        )
    return endpoints


def checked_address(target: DatabaseTarget) -> str:
    """The address to connect to, after every safety check."""
    if (target.host.lower(), target.port, target.database) in _platform_endpoints():
        raise UnsafeHostError("A connection cannot point at the platform's own database")
    try:
        infos = socket.getaddrinfo(
            target.host, target.port, type=socket.SOCK_STREAM
        )
    except socket.gaierror:
        raise DatabaseConnectorError(f"the host {target.host} could not be resolved") from None

    addresses = []
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global and not settings.DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS:
            raise UnsafeHostError(
                "The host resolves to a private or local address, which is not allowed"
            )
        addresses.append(str(address))
    if not addresses:
        raise DatabaseConnectorError(f"the host {target.host} has no address")
    return addresses[0]


def connect(target: DatabaseTarget, *, statement_timeout_ms: int = STATEMENT_TIMEOUT_MS):
    address = checked_address(target)
    try:
        return psycopg.connect(
            host=target.host,
            hostaddr=address,
            port=target.port,
            dbname=target.database,
            user=target.username,
            password=target.password,
            sslmode=target.sslmode,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            application_name="enterprise-knowledge-ai",
            options=(
                "-c default_transaction_read_only=on "
                f"-c statement_timeout={int(statement_timeout_ms)} "
                "-c idle_in_transaction_session_timeout=30000"
            ),
            autocommit=False,
        )
    except psycopg.OperationalError as exc:
        message = str(exc).strip().splitlines()[-1] if str(exc).strip() else ""
        raise DatabaseConnectorError(f"connection failed: {message[:300]}") from None


def _wrap(sql: str, max_rows: int) -> str:
    query = sql.strip()
    while query.endswith(";"):
        query = query[:-1].rstrip()
    if not query:
        raise DatabaseQueryError("The query is empty")
    # New lines around the query keep a trailing comment from swallowing
    # the closing parenthesis.
    return f"SELECT * FROM (\n{query}\n) AS eka_query LIMIT {int(max_rows) + 1}"


def _cut(value):
    if isinstance(value, str) and len(value) > MAX_VALUE_CHARS:
        return value[:MAX_VALUE_CHARS] + "..."
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{len(value)} bytes>"
    return value


def run_read_only_query(
    target: DatabaseTarget,
    sql: str,
    *,
    max_rows: int = MAX_ROWS,
    statement_timeout_ms: int = STATEMENT_TIMEOUT_MS,
) -> QueryResult:
    wrapped = _wrap(sql, max_rows)
    connection = connect(target, statement_timeout_ms=statement_timeout_ms)
    try:
        connection.read_only = True
        with connection.cursor() as cursor:
            try:
                cursor.execute(wrapped, prepare=True)
                rows = cursor.fetchmany(max_rows + 1)
                columns = tuple(column.name for column in cursor.description)
            except psycopg.errors.QueryCanceled:
                raise DatabaseQueryError(
                    f"The query took longer than {statement_timeout_ms / 1000:g} seconds"
                ) from None
            except psycopg.Error as exc:
                first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
                raise DatabaseQueryError(f"The query failed: {first_line[:300]}") from None
    finally:
        connection.rollback()
        connection.close()

    return QueryResult(
        columns=columns,
        rows=tuple(tuple(_cut(value) for value in row) for row in rows[:max_rows]),
        truncated=len(rows) > max_rows,
    )


CATALOG_SQL = """
    SELECT n.nspname, c.relname, c.relkind::text, c.reltuples::bigint,
           obj_description(c.oid, 'pg_class'),
           a.attname, format_type(a.atttypid, a.atttypmod), NOT a.attnotnull,
           col_description(c.oid, a.attnum)
    FROM pg_catalog.pg_class AS c
    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
    JOIN pg_catalog.pg_attribute AS a
      ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
    WHERE n.nspname = ANY(%(schemas)s)
      AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND has_table_privilege(c.oid, 'SELECT')
    ORDER BY n.nspname, c.relname, a.attnum
"""


def introspect(target: DatabaseTarget) -> dict:
    """What the agent may query: tables and views the role can read."""
    connection = connect(target)
    try:
        connection.read_only = True
        rows = connection.execute(
            CATALOG_SQL, {"schemas": list(target.schemas)}
        ).fetchall()
    except psycopg.Error as exc:
        raise DatabaseConnectorError(f"the schema could not be read: {type(exc).__name__}") from None
    finally:
        connection.rollback()
        connection.close()

    kinds = {"r": "table", "p": "table", "v": "view", "m": "view", "f": "table"}
    tables: dict[tuple[str, str], dict] = {}
    truncated = False
    for schema, name, kind, estimate, comment, column, type_, nullable, column_comment in rows:
        key = (schema, name)
        if key not in tables:
            if len(tables) >= MAX_TABLES:
                truncated = True
                continue
            tables[key] = {
                "schema": schema,
                "name": name,
                "kind": kinds.get(kind, "table"),
                # -1 means never analyzed: unknown, not empty.
                "rows_estimate": int(estimate) if estimate is not None and estimate >= 0 else None,
                "comment": comment,
                "columns": [],
            }
        columns = tables[key]["columns"]
        if len(columns) >= MAX_COLUMNS:
            truncated = True
            continue
        columns.append(
            {"name": column, "type": type_, "nullable": bool(nullable), "comment": column_comment}
        )

    return {
        "schemas": list(target.schemas),
        "tables": list(tables.values()),
        "truncated": truncated,
    }
