# Background jobs

Work that takes longer than a request (syncing a source, reading a
spreadsheet, building embeddings) runs in the worker, not in the API.
Migration `c6a2e9f4b1d7` creates the queue (`background_jobs`) in
PostgreSQL: no extra service, the same transactions and the same
row-level security as the rest of the data.

## How a job moves

```
queued -> running -> succeeded
             |-----> queued (retry after 30 s, 1 min, 2 min... at most 1 h)
             |-----> failed (after max_attempts, or no handler for the kind)
queued -> cancelled
```

A trigger refuses any other move, and a finished job never changes.

| Role | On `background_jobs` |
|---|---|
| `eka_runtime` (the API) | SELECT and INSERT, only for organizations it manages; a new job must be queued, untouched, and created by the caller. No UPDATE. |
| `eka_worker` (the worker) | SELECT, and UPDATE of the run columns only (`status`, `attempts`, `run_after`, `locked_by`, `locked_at`, `last_error`, `finished_at`). It cannot change what a job is (`kind`, `payload`). |

## Rules for handlers

- Register one with `@job_handler("source.sync")` in a module the worker
  imports. Kinds are lower case, with dots or underscores.
- The handler and the "succeeded" status commit together. If the handler
  raises, everything it wrote is rolled back and the job is retried, so a
  handler must be safe to run again.
- The payload names things (ids), never secrets.
- The worker sets `app.organization_id` to the job's organization before
  the handler runs; tables the worker will touch later get policies for
  `eka_worker` scoped to that setting.
- `dedupe_key` keeps one waiting or running job per organization, kind and
  key (one sync at a time per source).
- A job running for more than 15 minutes without finishing is taken as
  lost (its worker stopped) and queued again.

## Running the worker

Setting (name only; the value stays in your `.env`): `WORKER_DATABASE_URL`,
a login that holds `eka_worker`. In development the migration login can be
used, since a superuser is a member of every role.

From the backend folder:

```
python -m scripts.run_worker            # one pass
python -m scripts.run_worker --watch    # keep polling
```
