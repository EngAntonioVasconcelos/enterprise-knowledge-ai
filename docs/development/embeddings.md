# Embeddings and hybrid search (Phase 6, RAG Core)

## What an embedding is

An embedding model reads a text and returns a list of numbers (384 for
the model used here). The numbers place the text on a map of meanings:
texts that mean similar things get close vectors, even with different
words or in another language. "dias de ferias" lands near "vacation days"
and far from "parking". Search by meaning compares the question's vector
with every passage's vector (cosine distance) and returns the closest.

## The model

`intfloat/multilingual-e5-small` (MIT licence, 118M parameters, 100+
languages, 384 numbers per text), run locally on the CPU by fastembed
with ONNX Runtime. Free, private (no text leaves the machine), no GPU.
It expects the prefixes `query:` and `passage:`; the gateway adds them.

Download it once (about 470 MB, into `EMBEDDING_CACHE_DIR`, default
`backend/var/models`, ignored by Git) and see it work:

    python -m scripts.try_embeddings

The API and the worker never download: without the model, hybrid search
falls back to words and says so (`mode: keyword`, `note`), and vector jobs
retry later.

`EMBEDDING_PROVIDER`: `fastembed` (default), `hashing` (tests and CI: a
deterministic stand-in that only knows shared words) or `none`.

## Where vectors are computed

The sync cuts a new version into passages in its transaction, then queues
`document.embed` for that version (the worker may queue only this kind,
only for its own organization). The job computes the vectors in batches
of 32 and stores them in `chunk_embeddings` (migration c8e4f2a6b1d9), one
row per passage and model. A failure never undoes a sync.

Readers of a vector are the readers of its passage, hence of its
document. Only the worker writes vectors.

## Model agnostic

Every vector records its model; vectors of different models are never
compared. Changing model means computing new rows next to the old ones,
then switching, with no downtime. Each model gets its own partial HNSW
index at its size (this migration: e5-small, 384, cosine).

## Hybrid search

`GET /organizations/{id}/search/?q=...&mode=hybrid|keyword|semantic`
(default hybrid). Hybrid runs both searches (40 candidates each) and
merges them with Reciprocal Rank Fusion: each passage scores
1 / (60 + position) in every list it appears in. Each result shows its
`keyword_rank` and `semantic_rank`, so it is visible why it came up.
With row-level security filtering after the vector index, pgvector 0.8
iterative scans keep reading the index until enough visible rows exist.

## Not done yet

- Documents synchronized before this migration get vectors at their next
  new version.
- The vector table is used through SQL only; `migrations/env.py` tells
  `alembic check` to ignore it.
