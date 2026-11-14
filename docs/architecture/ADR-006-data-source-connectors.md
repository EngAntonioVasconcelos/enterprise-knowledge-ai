# ADR-006: Data source connectors
 
- Status: accepted (implementation in Phase 5)
- Date: 2026-11-14
 
## Context
 
Companies keep their knowledge in many places: documents in Google Drive or
SharePoint, figures in Excel files, records in their own databases, and
work in business applications such as a CRM. Google Drive was only the first
source. Each company must be able to connect as many sources, of as many
kinds, as it needs.
 
These sources are not alike. Text is answered by retrieval with citations.
Numbers are not: retrieving fragments of a spreadsheet and letting a language
model add them up produces confident, wrong totals.
 
## Decision
 
One connector layer with a common contract, and four kinds of source, each
answered in the way that fits its data.
 
| Kind | Examples | How questions are answered |
| --- | --- | --- |
| Documents | Google Drive, SharePoint, OneDrive, Confluence, Notion, S3 | Text and permissions are ingested, indexed (vectors and full text) and retrieved with citations |
| Tabular files | Excel (.xlsx), CSV, Google Sheets | Each sheet becomes a table; numeric questions are answered by a query, citing file, sheet and cell range |
| Databases | PostgreSQL, MySQL, SQL Server, Oracle, Snowflake, BigQuery | Live, read-only queries; data is not copied |
| Business applications | CRM, ERP, helpdesk, e-mail, calendar | Official APIs with the user's permissions; actions only as agent level 3 |
 
### Common contract
 
- A connection belongs to one organization. The connections table has forced
  row-level security from its first migration (ADR-005).
- Credentials are encrypted with a per-organization key (envelope encryption
  with a managed KMS). The API never returns them and they never reach logs.
  OAuth is preferred to stored passwords.
- Synchronization runs in the worker through the Postgres job queue:
  incremental, including permission changes and deletions. Every answer shows
  when its source was last synchronized.
- Permissions from the source are kept and applied in the query, so the
  assistant never retrieves what the user could not open at the source.
- Every query, synchronization and action is audited.
- No limit on the number or kind of sources. Safeguards that protect the
  customer's systems (query timeout, maximum rows, rate of API calls) are
  configurable by the organization's admins.
- Writing to a source (a database row, a CRM record, a sent e-mail) is an
  agent level 3 action: proposed, approved by a person, audited. Never
  automatic.
 
### Tabular files
 
- The original file is kept as uploaded. Each sheet is parsed into a table
  with detected headers and column types and stored as a columnar copy
  (Parquet) in the organization's storage, versioned on every change.
- Questions are answered by SQL run on that copy by an embedded analytical
  engine (DuckDB) in an isolated, read-only worker process. The SQL is
  generated, validated (single SELECT, allowed tables only) and shown with
  the answer.
- Values computed by Excel formulas are read as cached by Excel; formulas are
  not executed.
- Sheets that do not parse cleanly (several header rows, merged cells,
  tables side by side) are flagged for an admin to review instead of guessed.
- The text around tables (sheet names, notes, headers) is also indexed, so
  retrieval can find the right file before the query runs.
 
### Databases
 
- The company provides a read-only database user. Only single SELECT
  statements run, after parsing; admins choose which tables and columns the
  agent may use (none by default).
- Private networks are reached by a connection agent installed on the
  company's side, which connects outwards, so no inbound port is opened.
 
## Alternatives considered
 
- **Embedding spreadsheet rows as text.** Simple, reuses the document
  pipeline, but aggregates are impossible and numbers are paraphrased. Rejected
  for numeric answers; kept only for finding the right file.
- **Loading every sheet into PostgreSQL tables.** One engine and row-level
  security for free, but it means DDL at runtime for every upload, wide
  privileges for the runtime, and analytical load on the transactional
  database. To be compared with the chosen approach in a spike at the start of
  Phase 5.
- **Copying customer databases.** Fast queries, but stale data, duplicated
  personal data and a much larger compliance burden. Rejected.
 
## Consequences
 
- Phase 5 builds the connector contract first, then one connector of each
  kind in this order: Google Drive (documents), Excel and CSV upload (tabular
  files), PostgreSQL read-only (databases). Business applications follow with
  the agent in Phase 6.
- The worker and the job queue become part of the core architecture.
- A storage decision for originals and columnar copies (ADR-004) applies to
  tabular files too.
