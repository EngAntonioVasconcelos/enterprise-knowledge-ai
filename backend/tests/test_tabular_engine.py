import duckdb
import pytest

from app.services.tabular_engine import (
    QueryRefusedError,
    QueryTimeoutError,
    check_read_only,
    locked_connection,
    run_query,
)


@pytest.fixture
def sales(tmp_path):
    path = tmp_path / "sales.parquet"
    duckdb.sql(
        "COPY (SELECT range AS id, 'Region ' || (range % 3) AS region, "
        "range * 1.5 AS amount FROM range(3000)) "
        f"TO '{path.as_posix()}' (FORMAT parquet)"
    )
    return path


@pytest.fixture
def outside(tmp_path):
    path = tmp_path / "other-organization.csv"
    path.write_text("secret\nsalaries\n", encoding="utf-8")
    return path


def test_a_question_is_answered_from_the_allowed_dataset(sales):
    result = run_query(
        {"sales": sales},
        "SELECT region, count(*) AS n FROM sales GROUP BY 1 ORDER BY 1",
    )

    assert result.columns == ("region", "n")
    assert result.rows == (("Region 0", 1000), ("Region 1", 1000), ("Region 2", 1000))
    assert result.truncated is False


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv('{outside}')",
        "SELECT * FROM read_text('{outside}')",
        "SELECT * FROM '{outside}'",
        "COPY sales TO '{outside}.copy'",
        "ATTACH '{outside}.db'",
        "SET enable_external_access = true",
        "SET lock_configuration = false",
        "INSTALL httpfs",
        "LOAD httpfs",
    ],
)
def test_nothing_outside_the_dataset_can_be_reached(sales, outside, sql):
    db = locked_connection({"sales": sales})
    try:
        with pytest.raises(duckdb.Error):
            db.execute(sql.format(outside=outside.as_posix()))
        # The dataset itself still answers.
        assert db.execute("SELECT count(*) FROM sales").fetchone() == (3000,)
    finally:
        db.close()


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM sales",
        "CREATE TABLE copy AS SELECT * FROM sales",
        "SELECT 1; SELECT 2",
        "PRAGMA show_tables",
        "COPY sales TO 'x.csv'",
        "SET threads = 64",
        "this is not sql",
    ],
)
def test_only_one_select_is_accepted(sql):
    with pytest.raises(QueryRefusedError):
        check_read_only(sql)


def test_with_queries_are_selects():
    sql = "WITH t AS (SELECT 1 AS x) SELECT x FROM t"
    assert check_read_only(sql) == sql


def test_a_slow_query_is_stopped(sales):
    with pytest.raises(QueryTimeoutError):
        run_query(
            {"sales": sales},
            "SELECT sum(a.range * b.range) FROM range(100000) a, range(100000) b",
            timeout_seconds=0.2,
        )


def test_large_answers_are_cut(sales):
    result = run_query({"sales": sales}, "SELECT id FROM sales", max_rows=10)

    assert len(result.rows) == 10 and result.truncated is True


def test_table_names_are_checked(sales):
    with pytest.raises(ValueError):
        locked_connection({'sales"; DROP': sales})
