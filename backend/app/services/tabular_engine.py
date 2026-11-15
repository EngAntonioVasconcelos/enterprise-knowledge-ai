"""Answer questions over tabular data with a locked-down DuckDB (ADR-008).

Each question gets a fresh, in-memory DuckDB that can read only the
Parquet files of the datasets the person may open. The permission check
happens before, in PostgreSQL (RLS, as for documents); DuckDB never sees
anything else, so a generated query cannot reach other data even if it
tries.

Guards, all on by default:
- one statement, and it must be a SELECT (WITH ... SELECT included);
- no file, network or extension access once the views exist, and the
  configuration is locked so the query cannot turn it back on;
- a memory limit, few threads, a time limit and a row limit.
"""

import re
import threading
from dataclasses import dataclass
from pathlib import Path

import duckdb

from app.core.errors import InvalidInputError


MEMORY_LIMIT = "1GB"
THREADS = 2
TIMEOUT_SECONDS = 10.0
MAX_ROWS = 1000

TABLE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


class TabularQueryError(InvalidInputError):
    pass


class QueryRefusedError(TabularQueryError):
    """The query is not a single read-only SELECT."""


class QueryTimeoutError(TabularQueryError):
    pass


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple, ...]
    truncated: bool


def check_read_only(sql: str) -> str:
    try:
        statements = duckdb.extract_statements(sql)
    except duckdb.Error as exc:
        raise QueryRefusedError(f"The query is not valid SQL: {str(exc)[:200]}") from None
    if len(statements) != 1:
        raise QueryRefusedError("Exactly one statement is allowed")
    if statements[0].type != duckdb.StatementType.SELECT:
        raise QueryRefusedError("Only SELECT queries are allowed")
    return sql


def _literal(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def locked_connection(
    tables: dict[str, Path],
    *,
    memory_limit: str = MEMORY_LIMIT,
    threads: int = THREADS,
) -> duckdb.DuckDBPyConnection:
    """A DuckDB that sees these Parquet files as tables, and nothing else."""
    for name in tables:
        if not TABLE_NAME.match(name):
            raise ValueError(f"Invalid table name {name!r}")

    db = duckdb.connect(
        ":memory:", config={"memory_limit": memory_limit, "threads": threads}
    )
    try:
        for name, path in tables.items():
            db.execute(
                f'CREATE VIEW "{name}" AS SELECT * FROM read_parquet({_literal(path)})'
            )
        allowed = ", ".join(_literal(path) for path in tables.values())
        db.execute(f"SET allowed_paths = [{allowed}]")
        db.execute("SET enable_external_access = false")
        db.execute("SET autoload_known_extensions = false")
        db.execute("SET autoinstall_known_extensions = false")
        db.execute("SET lock_configuration = true")
    except BaseException:
        db.close()
        raise
    return db


def run_query(
    tables: dict[str, Path],
    sql: str,
    *,
    timeout_seconds: float = TIMEOUT_SECONDS,
    max_rows: int = MAX_ROWS,
) -> QueryResult:
    check_read_only(sql)
    db = locked_connection(tables)
    timer = threading.Timer(timeout_seconds, db.interrupt)
    timer.start()
    try:
        cursor = db.execute(sql)
        rows = cursor.fetchmany(max_rows + 1)
        columns = tuple(column[0] for column in cursor.description)
    except duckdb.InterruptException:
        raise QueryTimeoutError(
            f"The query took longer than {timeout_seconds:g} seconds"
        ) from None
    except duckdb.Error as exc:
        raise TabularQueryError(f"The query failed: {str(exc)[:300]}") from None
    finally:
        timer.cancel()
        db.close()

    return QueryResult(
        columns=columns,
        rows=tuple(rows[:max_rows]),
        truncated=len(rows) > max_rows,
    )
