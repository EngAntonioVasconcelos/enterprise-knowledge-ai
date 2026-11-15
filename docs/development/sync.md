# Synchronization

One engine brings every source into the archive
(`app/services/sync_service.py`). A connector only talks to its source
(`app/connectors/base.py`); versions, permissions, storage, retries and
audit are done once, the same way for all.

## A connector

```python
@register_connector("google_drive")
def build(context: ConnectionContext) -> SourceConnector: ...
```

It implements two methods:

- `list_changes(cursor)`: what changed since the cursor (`ChangeSet`:
  changed items with their permissions, removed ids, the new cursor, and
  `complete=True` when it lists everything the source has).
- `fetch_text(item)`: the item's extracted text.

It raises `ConnectorAuthError` when the source refuses the credentials
(the connection goes to `error` and waits for an admin) and
`ConnectorError` for anything temporary (the job is retried with backoff).

## What a sync does

Queued with `POST /organizations/{id}/connections/{id}/sync` (owners and
admins; answers 202 with the job id; asking twice queues one job), run by
the worker as the job `connection.sync`:

| Source reports | Archive does |
|---|---|
| a new or changed item | normalize the text; if the hash equals the current version, refresh title and permissions only; otherwise store the snapshot and make a new version current |
| a removed item, or an item missing from a complete listing | take the document out of retrieval at once (versions kept) |
| an item back after removal | bring it back |
| permissions | replace them and re-resolve the readers, every time |

Each item runs in its own savepoint: one broken file is counted in
`last_error` and the rest goes on. The cursor is saved at the end. A paused
or disconnected connection is not synchronized.

## Storage

`app/services/object_storage.py`: `LocalObjectStorage` in development
(`LOCAL_STORAGE_PATH`, default `var/storage`, ignored by Git), an
S3-compatible backend with hosting. Keys are ids and hashes only
(`org/connection/document/sha256/normalized.txt`), never titles, and
content-addressed, so retries are harmless.

## Next

Phase 6 adds chunking and embeddings between "snapshot stored" and
"version ready". The first real connector comes next.
