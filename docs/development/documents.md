# Documents and versions

Implements ADR-003 (versioning) on the storage model of ADR-004. Migration
`f3a8c6e1b9d4` reshapes the placeholder `documents` table (it refuses to
run if the table holds rows) and adds `document_versions`.

## Model

- **Document**: the stable identity of an item in a source, unique per
  connection and `external_id` (a Drive file id, an upload id). Status:
  `pending` (no version yet), `active` (has a current version), `failed`
  (its first version failed), `removed` (out of retrieval).
- **DocumentVersion**: one immutable snapshot. Holds the SHA-256 of the
  normalized text, size, source revision and modification time, and the
  object storage keys of the original and normalized files. The database
  numbers versions (1, 2, 3...) per document.

## Rules the database enforces

| Rule | How |
|---|---|
| A version moves only from `processing` to `ready` or `failed`, then never changes | trigger and column privileges |
| A document's current version is a ready version of that document | trigger |
| An `active` document has a current version | check constraint |
| `ready_at` and `removed_at` are stamped by the database | triggers |
| The worker writes only for the organization of its current job | row-level security |
| The API reads (owners and admins for now) and never writes | privileges |
| Nobody deletes a version directly | privileges (retention comes later) |

## Ingestion flow (worker)

`app/services/document_service.py`:

1. `upsert_document` for the source item.
2. `normalize_content` then `content_hash` on the extracted text; if the
   hash equals the current version's, `add_version` returns `None` and
   nothing is reprocessed.
3. Process the `processing` version (chunks and embeddings, Phase 6).
4. `mark_version_ready` and `activate_version`, or `fail_version`: on
   failure the previous version stays current.
5. `remove_document` when the item disappears from the source: out of
   retrieval at once, versions kept for retention.

Changes to the embedding model or chunking do not create versions: they
re-index the current one (ADR-003, 4.1).

## Next

Source permissions (who may see each document) come next; members get
access to documents through them. Object storage (local folder in
development, S3-compatible in production) comes with file upload.
