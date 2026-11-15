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

## Measured (15 November 2026, e5 + m3 INT8, 60 questions, 38 passages)

Recall@5 (MRR): words 0.56 (0.51), meaning 0.85 (0.77), hybrid weighted
0.87 (0.78), hybrid rrf 0.78 (0.68), hybrid + reranker 1.00 (1.00); leaks
0 everywhere. Time per search: 15 ms hybrid, 1650 ms with the reranker
reading 20 whole passages; 5.2 s for 20 passages of 1200 characters.

- Weighted fusion: kept as the default (MRR +0.10 over rrf, English
  questions on Portuguese documents 0.50 to 0.90, no group lost).
- Reranker: passes on quality, fails on time (1.65 s > 1.5 s). 1.00 is
  also optimistic: it read 20 of only 38 passages.

## AI-2b: a faster reranker, a harder test

Two settings control its cost: `RERANK_CANDIDATES` (how many of the first
results it reads, default 10) and `RERANK_MAX_CHARS` (how many characters
of each, default 800; 0 = whole passage). It also reads the document title
and section heading before the text, which tells it what the passage is
about even when cut.

The evaluation now runs on a large library by default: the 17 documents
plus 400 distractors (`tests/integration/retrieval_distractors.py`) that
reuse the questions' words without answering them ("ferias" in a summer
camp for employees' children, "forklift" in a maintenance contract):
about 880 passages instead of 38. It compares rerank-20, rerank-10 (whole
passages) and rerank-20-short, rerank-10-short (first 600 characters),
with the average and the 95th percentile time.

Rule fixed before measuring: on the large library, choose the cheapest
setting whose MRR is within 0.02 of the best reranker setting, with leaks
0, codes 1.00, average up to 1.5 s and 95th percentile up to 2.5 s. If no
setting fits the time, the reranker stays off and the answer step relies
on the weighted hybrid plus the question translation (AJ-2).

## Measured (15 November 2026, large library, about 880 passages)

Recall@5 (MRR): words 0.46 (0.45), meaning 0.70 (0.67), hybrid 0.70
(0.67), rerank-20 0.72 (0.72), rerank-10 0.70 (0.70), rerank-20-short 0.72
(0.72), rerank-10-short 0.70 (0.70); leaks 0. Average / p95 time: hybrid
56 / 76 ms; rerank-20 2.56 / 2.93 s; rerank-10 1.74 / 1.93 s;
rerank-10-short 1.47 / 1.72 s. try_reranker on the same CPU: 20 x 1200
characters 5.33 s, 20 x 600 2.84 s, 10 x 1200 2.56 s, 10 x 600 1.43 s.

What it showed:
- The larger library cost a lot (hybrid 0.87 to 0.70). Almost every miss
  was outside the first 10 results (rank -): the reranker cannot reorder
  an answer it never receives. Its gain was +0.03 MRR, below the +0.05
  required, and codes fell to 0.83 in every hybrid variant.
- Decision by the rule: the reranker stays off by default (API rerank is
  false). Within the time budget only rerank-10-short fits, so the
  defaults are RERANK_CANDIDATES=10 and RERANK_MAX_CHARS=600 for when it is
  turned on. It is measured again after the first stage improves.
- The problem is the first stage (recall). "formulario WS-09" was first by
  words but out of the top 10 in hybrid: its word vote (0.5, half of the
  meaningful words) lost to ten passages found by meaning. And the 400
  distractors include about 20 near copies of each subject (one per site),
  which can fill the first page on their own.

## AI-2c: fixing the first stage

- A passage with a code or number of the question counts double in the
  fusion (CODE_VOTE = 2.0).
- Near copies (passages sharing at least 60% of their words, numbers
  ignored) are moved below the distinct passages. The best copy keeps its
  place and reports `similar` (how many follow); nothing is removed, so
  the Porto version of a policy is still reachable.
- Each method proposes 100 candidates instead of 40, so moving copies down
  does not lose answers.
- Misses in the report now show the first 3 titles returned, to see what
  pushed the answer out.

Honest note: the near copies in the test come from our own generator (20
per subject is more than most companies have). Moving copies down is
still a product feature: per-site versions and duplicated files are common
and a first page of ten copies helps nobody.

Rule fixed before measuring: keep AI-2c if, on the large library, hybrid
MRR rises, codes return to 1.00, leaks stay 0 and hybrid stays under 150
ms on average; and on the small library no group loses more than one
question. Next for cross-language (pt-to-en 0.17 on the large library):
question translation in AJ-2, and measuring multilingual-e5-base.
