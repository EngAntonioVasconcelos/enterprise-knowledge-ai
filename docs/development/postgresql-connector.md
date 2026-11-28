# PostgreSQL connector (read-only)

A `postgresql` connection lets the agent answer questions from a
customer's live database. The data is never copied into the platform:
the worker describes the schema (the catalog) and, from Phase 7, runs the
agent's queries read-only.

## Creating a connection

Settings (not secret):

    {"host": "db.example.com", "port": 5432, "database": "sales",
     "sslmode": "require", "schemas": ["public"]}

- `sslmode`: require (default), verify-ca, verify-full; `disable` only
  when `DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS=true` (development).
- `schemas`: only these are described and queried (default public).
- `scope.roles` works as for every connection
  (`docs/development/connection-scope.md`).

Credentials go to the sealed store (ADR-007):
`PUT .../credentials` with `{"secret": {"username": "...", "password": "..."}}`.
Ask the customer for a role that can only SELECT the tables to share.

Then `POST .../sync`: for a database this queues `connection.introspect`,
which refreshes the catalog (`GET .../catalog`). If the database cannot be
reached, the connection goes to `error` with the reason.

## Safety

- The host is resolved once; private, local and link-local addresses are
  refused (so a connection cannot reach our own network or cloud metadata),
  and the session goes to the checked address. The platform's own
  databases are refused always.
- One exception, for the demo server: an exact host name listed in
  `DATABASE_CONNECTOR_ALLOWED_INTERNAL_HOSTS` may resolve to a private
  address and use `sslmode=disable`. Any other name is still refused, and a
  host of the platform's own databases is never accepted in that list.
- Sessions start read-only; each query runs in a READ ONLY transaction
  that is rolled back.
- A query is wrapped as one sub-query and sent as a prepared statement:
  anything but a single SELECT fails (INSERT, UPDATE, DELETE, data-modifying
  WITH, SET, a second statement, nextval).
- 15 s statement timeout, 10 s connect timeout, 1,000 rows, long values
  cut to 2,000 characters.

## Development

With a local PostgreSQL, set `DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS=true`
in `backend/.env` and use `sslmode` disable. Never in production.
