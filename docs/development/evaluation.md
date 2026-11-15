# Retrieval evaluation (Phase 6, AI-1)

## Why measure

Search quality can't be judged by trying three questions by hand. A change
that helps one question often hurts another. So every change to search
(chunking, the embedding model, a reranker, a new query rule) is judged
against the same fixed set of questions, with numbers, before it ships.

## The dataset

`backend/tests/evaluation/retrieval_dataset.json` is a fictional company,
"Atlantico Logistica": 14 internal documents (holidays, expenses,
onboarding, security, remote work, warehouse, fleet, returns, purchasing,
conduct, training, health insurance, and two restricted ones: salaries
and layoffs) and 43 questions. Each question says which document holds
the answer (`expect_doc`), a phrase from the right passage
(`expect_phrase`), and, for permission questions, a document that must
never appear (`expect_absent`).

Questions are grouped, because an average hides where search fails:

| Group | What it tests |
|---|---|
| pt-words / en-words | the question uses the same words as the document |
| pt-meaning / en-meaning | same meaning, different words ("descanso anual" for ferias) |
| en-to-pt / pt-to-en | question in one language, document in the other |
| exact-code | codes and numbers ("RH-12", "2.5") |
| permission | the answer exists but the user may not see it |

## The metrics

- **Recall@5**: in how many questions the right passage is in the first
  5 results. 0.80 means 8 out of 10 questions find it. The 5 matters
  because the answer step (AJ) will read the first few passages only.
- **MRR@10** (mean reciprocal rank): rewards the right passage being
  first. First place counts 1, second 0.5, third 0.33, ..., missing 0.
- **Leaks**: results the asking user may not see. Must always be 0; any
  leak fails the run.
- **ms/search**: time per search in the database.

## Two ways to run it

1. **In the tests and CI** (`tests/integration/test_retrieval_quality.py`),
   with the `hashing` stand-in embedder. It checks that leaks are 0 and
   that recall stays above floors set from the measured values, so a
   change that makes search worse fails CI.
2. **With the real model**, to take decisions (reranker, model):

        python -m scripts.evaluate_retrieval

   It runs in the disposable test database (`eka_test`) inside a
   transaction that is rolled back, prints the table and the questions
   each mode missed, and saves the numbers in `backend/var/eval/`
   (ignored by Git) for later comparison.

## Findings so far (hashing stand-in, November 2026)

- Search by words used `websearch_to_tsquery`, which requires every word.
  A natural question ("quantos dias de ferias tenho por ano?") then
  matched almost nothing: Recall@5 0.15. It now searches for any of the
  meaningful words (stopwords removed, codes kept whole) and ranks
  passages with more of them higher: 0.69. Quotes, `-word` and `or`
  still work as advanced syntax.
- Equal scores were ordered by random ids, so the same question could
  return a different order. Ties are now broken by title and position.
- No stemming: "empilhadores" does not find "empilhador". The `simple`
  configuration is kept on purpose (multilingual); meaning search and a
  reranker are expected to cover this. To be measured with the real model.
- Cross-language questions are the weak point (0.20 to 0.25 with the
  stand-in, which only knows shared words). This is what the real model
  must fix; measure it before choosing a reranker.
