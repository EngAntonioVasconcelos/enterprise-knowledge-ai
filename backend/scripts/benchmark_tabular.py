"""Spike: DuckDB or PostgreSQL for questions over Excel and CSV (ADR-008).

Generates a synthetic sales table (no real data), then measures, on the
same machine:

- PostgreSQL: COPY into a TEMPORARY table of the disposable test database
  (eka_test, port 1999), then three typical questions;
- DuckDB: CSV to Parquet (the stored form), then the same questions, each
  in a fresh, locked-down DuckDB that can read only that dataset's file
  (app/services/tabular_engine.py);
- reading an Excel sheet (needed by both options).

Nothing permanent is written to any database: temporary tables vanish
when the script's connection closes. Files go to a temporary folder that
is removed at the end.

Run from the backend folder, with the test database running:
    python -m scripts.benchmark_tabular            (1,000,000 rows)
    python -m scripts.benchmark_tabular 200000
"""

import csv
import os
import random
import shutil
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import duckdb
import psycopg
from openpyxl import Workbook, load_workbook
from sqlalchemy.engine import make_url

from app.services.tabular_engine import locked_connection


TEST_DATABASE = "eka_test"
TEST_ADMIN_URL = os.environ.get(
    "EKA_TEST_ADMIN_DATABASE_URL",
    "postgresql+psycopg://eka_test_admin:local-test-admin-only"
    f"@127.0.0.1:1999/{TEST_DATABASE}",
)

COLUMNS = ("sold_on", "region", "product", "channel", "customer_id", "quantity", "unit_price")

QUESTIONS = {
    "revenue by region and month": """
        SELECT region, date_trunc('month', sold_on) AS month,
               round(sum(quantity * unit_price), 2) AS revenue
        FROM sales GROUP BY 1, 2 ORDER BY 1, 2
    """,
    "top 10 products in 2025": """
        SELECT product, round(sum(quantity * unit_price), 2) AS revenue
        FROM sales
        WHERE sold_on >= DATE '2025-01-01' AND sold_on < DATE '2026-01-01'
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """,
    "distinct customers per channel": """
        SELECT channel, count(DISTINCT customer_id) AS customers
        FROM sales WHERE quantity >= 3 GROUP BY 1 ORDER BY 1
    """,
}


def generate_csv(path: Path, rows: int) -> None:
    rng = random.Random(42)
    regions = [f"Region {i}" for i in range(8)]
    products = [f"Product {i:03d}" for i in range(200)]
    channels = ["store", "online", "partner", "phone"]
    start = date(2023, 1, 1)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for _ in range(rows):
            writer.writerow(
                (
                    (start + timedelta(days=rng.randrange(1095))).isoformat(),
                    rng.choice(regions),
                    rng.choice(products),
                    rng.choice(channels),
                    rng.randrange(50_000),
                    rng.randrange(1, 10),
                    f"{rng.uniform(1, 500):.2f}",
                )
            )


def best_of(runs: int, action) -> tuple[float, object]:
    best, result = None, None
    for _ in range(runs):
        started = time.perf_counter()
        result = action()
        elapsed = time.perf_counter() - started
        best = elapsed if best is None else min(best, elapsed)
    return best, result


def postgres(csv_path: Path) -> dict:
    url = make_url(TEST_ADMIN_URL)
    if url.database != TEST_DATABASE:
        raise SystemExit(f"Refusing to run: the database must be {TEST_DATABASE}.")
    timings = {}
    with psycopg.connect(url.set(drivername="postgresql").render_as_string(hide_password=False)) as conn:
        conn.execute(
            "CREATE TEMPORARY TABLE sales (sold_on date, region text, product text, "
            "channel text, customer_id integer, quantity integer, unit_price numeric(10,2))"
        )
        started = time.perf_counter()
        with conn.cursor().copy(
            "COPY sales FROM STDIN WITH (FORMAT csv, HEADER true)"
        ) as copy, csv_path.open("rb") as handle:
            while chunk := handle.read(1 << 20):
                copy.write(chunk)
        conn.execute("ANALYZE sales")
        timings["import"] = time.perf_counter() - started
        for name, sql in QUESTIONS.items():
            timings[name], rows = best_of(3, lambda sql=sql: conn.execute(sql).fetchall())
            timings[name + " rows"] = len(rows)
        conn.rollback()
    return timings


def isolation_holds(parquet: Path, outside: Path) -> bool:
    db = locked_connection({"sales": parquet})
    attempts = (
        f"SELECT * FROM read_csv('{outside.as_posix()}')",
        "SET enable_external_access = true",
        "COPY sales TO 'escape.csv'",
        "INSTALL httpfs",
        f"ATTACH '{outside.as_posix()}.db'",
    )
    try:
        for sql in attempts:
            try:
                db.execute(sql)
            except duckdb.Error:
                continue
            print(f"  NOT ISOLATED: {sql}")
            return False
        return db.execute("SELECT count(*) FROM sales").fetchone()[0] > 0
    finally:
        db.close()


def duck(csv_path: Path, folder: Path) -> dict:
    timings = {}
    parquet = folder / "sales.parquet"
    started = time.perf_counter()
    with duckdb.connect(":memory:") as db:
        db.execute(
            f"COPY (SELECT * FROM read_csv('{csv_path.as_posix()}', header = true)) "
            f"TO '{parquet.as_posix()}' (FORMAT parquet)"
        )
    timings["import"] = time.perf_counter() - started
    timings["stored MB"] = parquet.stat().st_size / 1e6

    for name, sql in QUESTIONS.items():
        def run(sql=sql):
            db = locked_connection({"sales": parquet})
            try:
                return db.execute(sql).fetchall()
            finally:
                db.close()

        timings[name], rows = best_of(3, run)
        timings[name + " rows"] = len(rows)

    timings["isolation"] = isolation_holds(parquet, csv_path)
    return timings


def excel(folder: Path, rows: int = 50_000) -> dict:
    path = folder / "sheet.xlsx"
    book = Workbook(write_only=True)
    sheet = book.create_sheet("Sales")
    sheet.append(COLUMNS)
    rng = random.Random(7)
    for _ in range(rows):
        sheet.append(["2025-01-01", "Region 1", "Product 001", "store", rng.randrange(50_000), 2, 9.5])
    book.save(path)

    def read():
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            return sum(1 for _ in workbook["Sales"].iter_rows(values_only=True))
        finally:
            workbook.close()

    seconds, count = best_of(1, read)
    return {"rows": count - 1, "read seconds": seconds}


def main() -> int:
    rows = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    folder = Path(tempfile.mkdtemp(prefix="eka-tabular-"))
    try:
        csv_path = folder / "sales.csv"
        generate_csv(csv_path, rows)
        print(f"Synthetic sales: {rows:,} rows, CSV {csv_path.stat().st_size / 1e6:.1f} MB")

        results = {"PostgreSQL": postgres(csv_path), "DuckDB": duck(csv_path, folder)}
        for name in ("import", *QUESTIONS):
            pg, dk = results["PostgreSQL"][name], results["DuckDB"][name]
            print(f"  {name:32} PostgreSQL {pg:7.3f} s   DuckDB {dk:7.3f} s")
        for name in QUESTIONS:
            same = results["PostgreSQL"][name + " rows"] == results["DuckDB"][name + " rows"]
            print(f"  same number of answer rows ({name}): {same}")
        print(f"  DuckDB stored size: {results['DuckDB']['stored MB']:.1f} MB (Parquet)")
        print(f"  DuckDB reads only the allowed file: {results['DuckDB']['isolation']}")

        sheet = excel(folder)
        print(f"Excel: {sheet['rows']:,} rows read in {sheet['read seconds']:.2f} s")
        return 0 if results["DuckDB"]["isolation"] else 1
    finally:
        shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
