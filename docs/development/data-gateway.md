# The data gateway and the agent's data tool (Phase 7, AL-4)

The agent can answer from a customer's PostgreSQL database, read-only.
The API cannot open database credentials (ADR-007: only processes with the
master private key can), so the queries go through the **data gateway**, a
small internal service. Nothing of a customer database is copied or kept.

    browser -> web app -> API (agent) -> data gateway -> customer database

## What runs where

| | API | Data gateway |
|---|---|---|
| Who it serves | People (Auth0 sessions) | Only the API (DATA_GATEWAY_TOKEN) |
| Master private key | No (production) | Yes |
| Database role | eka_runtime, as the person | eka_worker, scoped to one organization |
| Reachable | Through the web app | Private network only, no published port |

The gateway answers two calls:

- `POST /v1/connections` `{organization_id, role}`: the active PostgreSQL
  connections with a catalog that the role may use (`scope.roles`).
- `POST /v1/query` `{organization_id, role, connection_id, sql}`: one query
  through the connector's read-only path (`docs/development/postgresql-connector.md`)
  with the agent's limits: `DATA_QUERY_MAX_ROWS` (50) rows and
  `DATA_QUERY_TIMEOUT_MS` (5,000 ms).

It logs neither the query nor the rows. Without `DATA_GATEWAY_TOKEN` it
refuses every call; without `DATA_GATEWAY_URL` the API has no data tool and
the agent answers from documents only.

## How the agent uses it

When the person may use at least one database, a first short call
(prompt `data_route_v1`, AL-4g) chooses DATA or DOCUMENTS from the
question and the catalog; anything but DATA goes to the documents. Then a
call (prompt `data_query_v2`, which also gives today's date) sees the question and the catalogs (table and
column names, types, comments; never rows) and replies with
`DATABASE: n` and a `SQL:` query, or `NONE`.

1. A query runs through the gateway; its rows go to the model (prompt
   `data_answer_v2`) between `<data id="D1">` tags.
2. The answer must cite `[D1]`, and every number in it must be in the rows
   (20.00 may be written 20, 10.50 may be 10,5) or in the question.
3. The relevance check of AL-2 runs as for documents.
4. A query the database refuses for its SQL (error class 42, such as an
   unknown column, or 22, such as a bad date) gets one repair (prompt
   `data_fix_v1`): the model sees its query and the database's error, both
   as data, and writes another. Timeouts and other errors are not repaired.
5. NONE, a refused or failing query, or no rows: the documents get their
   turn while the budget allows (AL-2 limits). An answer that fails a
   check is never shown.

Choosing, writing, answering and checking cost 4 model steps: with the
default budget (4) there is no room for a repair or, after a refused data
answer, for the documents. Owners and admins can raise the budget (up to
8) when the measurement says it pays.

Customer text (connection names, table comments, values) cannot close the
tags around it or fill a prompt placeholder. The prompts say it is data.

The person sees the rows used and the query ("See the data", AL-4b). The
answer text is kept in their private history like any answer; the rows
are not.

## Diagnosis (AL-4d)

The API logs one line per answer (logger `eka.answers`, INFO), for
example:

    answer prompt=answer-v3-... sources=0 abstained=False steps=4 tools=2 data=answered+repaired issues=0 ms={...}

`data` says how the data tool went: `none` (the model chose documents or
did not follow the form), `failed:<sqlstate>` (the database refused the
query, with PostgreSQL's error code, for example 42703 unknown column or
42601 syntax), `empty` (no rows), `refused` (the answer failed a check) or
`answered`, with `+repaired` after a repair. With `refused` and `relevant=False`, the
line before says what the relevance check replied
(`relevance verdict=...`). Neither the question, the
query, the database's error text nor the rows are ever logged.

    docker compose -f ../infrastructure/dev/docker-compose.yml --profile app logs --since 10m api | Select-String "answer prompt"

## Audit

Each data query is written to `audit_events` (`agent.tool_call`, tool
`query_data`) with the connection, the step, the row count and the time
(migration `d7e3b9c5a2f8`). No person, no question, no query, no rows. The
database refuses `query_data` without a connection of the same
organization.

## Development

`DATA_GATEWAY_TOKEN` is generated into `backend/.env` by the AL-4a block
(32 random bytes, never shown). The compose file starts the gateway with
the app profile and points the API at `http://data-gateway:8100`.

To try it end to end, use the invented sales database
(`demo-database.md`).

## Production (Phase 10)

The gateway runs beside the worker, on the private network, with its own
login that holds `eka_worker` and the master private key; the API has
neither. The token is rotated like any secret.
