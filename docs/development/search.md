# Passages and search (Phase 6, RAG Core)

## Passages (chunks)

When the sync stores a new version of a document, the worker cuts its text
into passages (`app/services/chunking.py`) in the same transaction:

- blocks are paragraphs and headings; a sentence is never cut unless it is
  longer than 2,000 characters;
- a heading (Markdown `#`, numbered like `4.2 Holidays`, or a short line in
  capitals) starts a new passage and is kept as its `heading`;
- passages are packed to about 1,200 characters (300 tokens); a short last
  paragraph is repeated at the start of the next passage (overlap);
- each passage keeps its exact position: `content == text[start:end]`.

Passages live in `document_chunks` (migration b5d9e2a7c4f1). Readers of a
passage are exactly the readers of its document: the policy asks the
`documents` table, so source permissions, connection scope and membership
apply without being repeated. Only the worker writes passages; nobody
updates them.

## Search by words

`GET /organizations/{id}/search/?q=...&limit=20` (every role) returns
passages of the current version of active documents the caller may open,
ranked by PostgreSQL full text (`simple` configuration, so it works the
same in Portuguese and English). Accents and case are ignored
(`eka_search_text`, a database function that removes accents). Web-style queries work:
`"exact phrase"`, `-exclude`, `or`.

Search by meaning (vectors, pgvector) joins this in the next step, making
the search hybrid.

## Not done yet

- Documents synchronized before this migration get passages at their next
  new version.
- The full-text column `content_tsv` and its index exist only in the
  database; `migrations/env.py` tells `alembic check` to ignore them.
