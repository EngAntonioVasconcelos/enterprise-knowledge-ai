# Reranking and weighted fusion (Phase 6, AI-2)

## Two problems the first measurement showed

The real model measurement (AI-1, `docs/development/evaluation.md`) found:

1. Hybrid search found the right passage as often as search by meaning
   (Recall@5 0.92) but placed it lower (MRR 0.79 against 0.87). For English
   questions on Portuguese documents: 0.27 against 0.88. Cause: Reciprocal
   Rank Fusion gives every passage found by words a full vote. In another
   language, words only find passages that share a common word ("days",
   "policy"); those passages, also somewhere in the meaning list, outvoted
   the right one, which only meaning could find.
2. Some passages were not near the top in any method, for example
   "quem pode conduzir empilhadores?" whose answer is written in English
   ("forklift licence").

## Fix 1: weighted fusion (free)

A passage found by words now votes in proportion to its coverage, the
share of the question's meaningful words it contains, and only if it
matches at least half of them or one of the question's codes and numbers
("WS-09", "4400"). Search by words also orders its own list by codes
matched, then words matched, then the PostgreSQL rank. The first fusion
stays available as `fusion="rrf"` to compare. Each result shows its
`coverage`.

Trade-off: a paraphrase ("descanso" for "ferias") shares few words with
the passage, so its word vote is dropped; search by meaning carries those
(e5 measured 1.00 on Portuguese paraphrases). With the hashing stand-in,
which does not understand meaning, weighted hybrid is lower than the first
fusion; that is expected and is why the decision uses the real model.

## Fix 2: reranker (a second, slower look)

Words and meaning are fast because they never read the question and a
passage together. A cross-encoder reads both in one pass and scores how
well the passage answers the question. Too slow for the whole library, so
it reorders only the first 20 results (`RERANK_CANDIDATES`).

Model: `BAAI/bge-reranker-v2-m3` in its INT8 ONNX form, through fastembed:
Apache 2.0 (commercial use allowed), multilingual including Portuguese,
about 570 MB, CPU only. Chosen over:
- `jinaai/jina-reranker-v2-base-multilingual`: CC BY-NC (no commercial use);
- `ms-marco-MiniLM` and `bge-reranker-base`: small and fast, but trained
  for English (and Chinese); our users ask in Portuguese;
- the full-precision `bge-reranker-v2-m3` (2.3 GB): four times the
  download and memory, and slower on a CPU; INT8 usually loses little
  quality. Can be measured later if the INT8 numbers disappoint.

It runs on the CPU on purpose: the product must work on ordinary servers
and laptops; a GPU is an optional speed-up later, not a requirement.

It never sees passages the person may not read: it only reorders results
that row-level security already filtered (leaks stay 0 with it).

Download once (into `EMBEDDING_CACHE_DIR`) and see it work and how long it
takes on your computer:

    python -m scripts.try_reranker

`RERANK_PROVIDER`: `fastembed` (default), `overlap` (tests and CI, counts
shared words) or `none`. The API never downloads; without the model a
reranked search returns the normal order and says so in `note`.

API: `GET .../search/?q=...&rerank=true` (default false). Each result then
has `rerank_score` and the response `reranked: true`.

## How the decision is made

`python -m scripts.evaluate_retrieval` compares, on the same 60 questions:
`keyword`, `semantic`, `hybrid` (weighted, default), `hybrid-rrf` (first
fusion) and `hybrid+rerank`, with time per search. Rules fixed before
measuring:
- weighted fusion stays the default only if its MRR is higher than
  hybrid-rrf and no group loses more than one question in Recall@5;
- the reranker is used where its MRR gain is at least 0.05, codes stay at
  1.00, leaks 0, and its time fits the place: for the answer step (AJ),
  where the language model itself takes seconds, up to 1.5 s is
  acceptable; the search box stays without it (it must feel instant).
