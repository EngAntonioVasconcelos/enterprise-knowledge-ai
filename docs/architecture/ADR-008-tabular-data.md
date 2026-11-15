# ADR-008: Tabular data is queried with DuckDB over Parquet

Status: accepted (Phase 5, 15 Nov 2026)

## Context

Excel sheets, CSV files and Google Sheets hold numbers people ask about
("revenue by region last quarter"). Those questions are answered by a
query, not by retrieving text passages (ADR-006). The agent will write
SQL; the platform must run it fast, and it must never reach data the
person may not open, even when the SQL is wrong or hostile.

Options compared:

1. PostgreSQL: import each sheet into its own table and query it there.
2. DuckDB: store each sheet as a Parquet file in object storage and query
   it with an in-process DuckDB.

## Measurements

`python -m scripts.benchmark_tabular` (synthetic sales, 1,000,000 rows,
CSV 54 MB). Development sandbox, best of three runs; numbers from the
developer's machine are added below when available.

| Step | PostgreSQL | DuckDB |
|---|---|---|
| Import | 0.70 s | 0.38 s (to Parquet, 12.6 MB) |
| Revenue by region and month | 0.39 s | 0.05 s |
| Top 10 products in 2025 | 0.12 s | 0.04 s |
| Distinct customers per channel | 0.66 s | 0.06 s |

DuckDB times include opening a fresh, locked-down database for every
question. Both engines return the same answers. Reading a 50,000-row
Excel sheet takes about 3 s with openpyxl in either option: Excel parsing,
not the engine, is the slow step, and it happens in the worker.

## Decision

DuckDB over Parquet, with the permission decision kept in PostgreSQL.

- A tabular file is a dataset: a document of a tabular connection, with
  versions and source permissions exactly like documents (ADR-003,
  ADR-004). Each version stores one Parquet file per sheet, under a key
  made of ids and hashes only.
- To answer, the API first asks PostgreSQL (RLS) which datasets the
  person may open. Only those files are given to DuckDB.
- Each question runs in a new in-memory DuckDB
  (`app/services/tabular_engine.py`): the allowed files are exposed as
  views; then file, network and extension access is turned off and the
  configuration locked, so the query cannot turn it back on. One SELECT
  statement only; 1 GB memory, 2 threads, 10 seconds, 1,000 rows.
  Tests prove that reading other files, copying out, attaching
  databases, installing extensions and changing settings all fail.

## Why not PostgreSQL

- Every upload would create tables at run time: DDL outside migrations,
  privileges and RLS to repeat on tables that did not exist before, and
  the schema check (`alembic check`) would see them.
- A wrong query competes with the platform's own transactions on the
  same server; DuckDB runs apart, with its own limits.
- It was 3 to 11 times slower on the analytical questions measured.

PostgreSQL remains the system of record (identities, permissions,
versions, audit). Live PostgreSQL databases of customers are a separate
connector (read-only), not this path.

## Consequences

- New dependencies: `duckdb`, `openpyxl` (Excel reading).
- Row-level permissions inside one sheet are not supported: access is
  per dataset, as the source grants it.
- Messy sheets (merged cells, several tables in one sheet, header rows
  further down) need a cleaning step in the worker before Parquet; it is
  built with the spreadsheet upload connector.
- The DuckDB query runs inside the API process for now; if memory use
  becomes a problem it moves to a separate query worker without changing
  the contract.
