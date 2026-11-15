import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.connectors import postgresql
from app.core.config import settings
from scripts.prepare_test_database import TEST_ADMIN_URL


pytestmark = pytest.mark.integration


@pytest.fixture
def demo(postgres_engine, monkeypatch):
    """A customer schema with a table and a view, committed for real
    (the connector opens its own connections), removed afterwards."""
    schema = f"customer_{uuid.uuid4().hex[:8]}"
    engine = create_engine(TEST_ADMIN_URL)
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(
            f"CREATE TABLE {schema}.orders (id serial PRIMARY KEY, "
            "customer text NOT NULL, amount numeric(10,2), note text)"
        ))
        conn.execute(text(f"COMMENT ON TABLE {schema}.orders IS 'One row per order'"))
        conn.execute(text(
            f"INSERT INTO {schema}.orders (customer, amount, note) VALUES "
            "('Ana', 10.50, 'first'), ('Rui', 20.00, repeat('x', 5000)), "
            "('Ana', 5.25, NULL)"
        ))
        conn.execute(text(
            f"CREATE VIEW {schema}.totals AS SELECT customer, sum(amount) AS total "
            f"FROM {schema}.orders GROUP BY customer"
        ))

    url = make_url(TEST_ADMIN_URL)
    monkeypatch.setattr(settings, "DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS", True)
    # The test customer database is the test platform database itself.
    monkeypatch.setattr(postgresql, "_platform_endpoints", lambda: set())
    target = postgresql.build_target(
        {
            "host": url.host or "127.0.0.1",
            "port": url.port or 5432,
            "database": url.database,
            "sslmode": "disable",
            "schemas": [schema],
        },
        {"username": url.username, "password": url.password or "unused"},
    )
    try:
        yield schema, target
    finally:
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        engine.dispose()


def _count(schema):
    engine = create_engine(TEST_ADMIN_URL)
    try:
        with engine.connect() as conn:
            return conn.execute(text(f"SELECT count(*) FROM {schema}.orders")).scalar()
    finally:
        engine.dispose()


def test_the_catalog_describes_tables_and_views_only_of_the_chosen_schemas(demo):
    schema, target = demo

    catalog = postgresql.introspect(target)

    tables = {t["name"]: t for t in catalog["tables"]}
    assert set(tables) == {"orders", "totals"}
    assert all(t["schema"] == schema for t in catalog["tables"])
    assert tables["orders"]["kind"] == "table"
    assert tables["orders"]["comment"] == "One row per order"
    assert [c["name"] for c in tables["orders"]["columns"]] == [
        "id", "customer", "amount", "note",
    ]
    assert tables["orders"]["columns"][1] == {
        "name": "customer", "type": "text", "nullable": False, "comment": None,
    }
    assert tables["totals"]["kind"] == "view"


def test_a_select_is_answered_with_limits(demo):
    schema, target = demo

    result = postgresql.run_read_only_query(
        target, f"SELECT customer, total FROM {schema}.totals ORDER BY customer;"
    )
    assert result.columns == ("customer", "total")
    assert [row[0] for row in result.rows] == ["Ana", "Rui"]

    cut = postgresql.run_read_only_query(
        target, f"SELECT note FROM {schema}.orders ORDER BY id", max_rows=2
    )
    assert cut.truncated is True and len(cut.rows) == 2
    assert len(cut.rows[1][0]) == postgresql.MAX_VALUE_CHARS + 3


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM {s}.orders",
        "UPDATE {s}.orders SET amount = 0",
        "INSERT INTO {s}.orders (customer) VALUES ('x')",
        "WITH gone AS (DELETE FROM {s}.orders RETURNING id) SELECT * FROM gone",
        "SELECT 1) AS a; DELETE FROM {s}.orders; SELECT (1",
        "SELECT 1; DELETE FROM {s}.orders",
        "SET TRANSACTION READ WRITE",
        "CREATE TABLE {s}.stolen AS SELECT * FROM {s}.orders",
        "SELECT nextval('{s}.orders_id_seq')",
    ],
)
def test_anything_but_reading_is_refused(demo, sql):
    schema, target = demo

    with pytest.raises(postgresql.DatabaseQueryError):
        postgresql.run_read_only_query(target, sql.format(s=schema))

    assert _count(schema) == 3


def test_a_comment_cannot_reach_outside_the_query(demo):
    schema, target = demo

    result = postgresql.run_read_only_query(
        target, f"SELECT 1 AS one -- ) AS eka_query; DELETE FROM {schema}.orders; --"
    )

    # The comment ends at the line break the wrapper adds.
    assert result.rows == ((1,),)
    assert _count(schema) == 3


def test_a_slow_query_is_stopped(demo):
    _, target = demo

    with pytest.raises(postgresql.DatabaseQueryError) as error:
        postgresql.run_read_only_query(
            target, "SELECT pg_sleep(5)", statement_timeout_ms=200
        )
    assert "longer than" in str(error.value)


def test_wrong_credentials_are_a_connection_error(demo):
    _, target = demo
    url = make_url(TEST_ADMIN_URL)
    if not url.password:
        pytest.skip("this test database does not check passwords")
    wrong = postgresql.DatabaseTarget(**{**target.__dict__, "password": "wrong"})

    with pytest.raises(postgresql.DatabaseConnectorError) as error:
        postgresql.introspect(wrong)
    assert "wrong" not in str(error.value)
