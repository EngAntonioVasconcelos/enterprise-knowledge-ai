# Data connections

A data connection is a source an organization has connected (ADR-006):
a Google Drive, uploaded files, a database. Migration `d8b4f1a7c3e5`
creates `data_connections`. Credentials never live here: they get their
own encrypted store (next block, ADR-007), and settings that look like a
secret (`password`, `token`, `api_key`...) are refused by the API.

## Providers and kinds

The client sends the provider; the kind is derived from it, so the two can
never disagree. The kind decides how questions are answered.

| Provider | Kind | Answered by |
|---|---|---|
| `google_drive` | documents | retrieval with citations |
| `file_upload` | documents | retrieval with citations |
| `spreadsheet_upload` | tabular | queries on the sheets |
| `postgresql` | database | live read-only queries |

New providers are added to `PROVIDERS` in
`app/services/connection_service.py`; nothing else changes.

## Who can do what

| Role | On `data_connections` |
|---|---|
| `eka_runtime` (the API) | Owners and admins of the organization: read, create (active, by the caller), rename, pause, resume, change settings, disconnect. No DELETE. |
| `eka_worker` | Only the connections of the organization of its current job; may change `status`, `last_synced_at`, `last_error`. |
| triggers | `disconnected` is final; `updated_at` and `disconnected_at` are stamped by the database; every change is in the audit log (settings without their values). |

## API

All under `/api/v1/organizations/{organization_id}/connections`, owners and
admins only:

| Method | Path | What |
|---|---|---|
| GET | `/` | list (`?include_disconnected=true` for all) |
| POST | `/` | connect a source |
| GET | `/{id}` | one connection |
| PATCH | `/{id}` | rename, pause or resume, change settings |
| POST | `/{id}/disconnect` | disconnect; final, nothing is deleted |
