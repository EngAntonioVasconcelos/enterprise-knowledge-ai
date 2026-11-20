"""Measure the answers, not only the search (Phase 6, AJ-1).

Uses the same dataset and library as the retrieval evaluation
(retrieval_harness). Every question is asked as Rui, a member who cannot
read the confidential documents, through answer_question: search with the
reranker, the versioned prompt, the configured model and the checks.

Per question group:
- correct: answered, the expected passage is among the cited sources, and
  every number of the expected phrase is in the answer ("25 dias uteis":
  the answer must say 25). Language-independent, so an English answer
  about a Portuguese document counts;
- wrong: answered, but not from the expected passage or without its
  numbers;
- abstained: the honest "I could not find a reliable answer". On
  permission questions that is the right outcome;
- unverified: answers the checks refused (wrong citation or a number not
  in the sources); they were not shown, but they say how often the model
  invents;
- leaks: confidential documents among the sources or citations (must be 0);
- NAO_SEI mixed into answers: the model wrote the no-answer marker next to
  an answer (it is removed before showing; fewer is better);
- other language: answers (correct or wrong) not written in the language
  of the question, by the same small-word test the service uses.
Plus the average and 95th percentile time per answer.

There is no language model judging the answers: the checks are plain and
repeatable. They do not judge style or completeness; read a sample.
"""

import time
from collections import defaultdict

from app.services.answer_service import answer_question, numbers_in, question_language
from tests.integration.retrieval_harness import _as_runtime, _passages, _plain


def evaluate_answers(
    db, world, dataset: dict, limit: int | None = None, prompt_version: str | None = None
) -> dict:
    _as_runtime(db, world.rui)
    questions = dataset["questions"][:limit] if limit else dataset["questions"]
    groups = defaultdict(lambda: defaultdict(int))
    leaks, mixed, times, answers = 0, 0, [], []
    for question in questions:
        started = time.perf_counter()
        result = answer_question(
            db,
            organization_id=world.organization,
            question=question["query"],
            prompt_version=prompt_version,
        )
        mixed += result.mixed_abstain
        times.append(time.perf_counter() - started)

        passages = _passages(db, [s.hit.chunk_id for s in result.sources])
        given = {s.number: passages.get(s.hit.chunk_id, ("", "")) for s in result.sources}
        cited = [given[n] for n in result.cited if n in given]

        if question["category"] == "permission":
            restricted = set(question["expect_absent"])
            if any(doc in restricted for doc, _ in given.values()):
                leaks += 1
            outcome = "abstained" if result.abstained else "answered"
        elif result.abstained:
            outcome = "unverified" if not result.verified else "abstained"
        else:
            phrase = _plain(question["expect_phrase"])
            from_passage = any(
                doc == question["expect_doc"] and phrase in content for doc, content in cited
            )
            numbers_ok = numbers_in(question["expect_phrase"]) <= numbers_in(result.answer)
            outcome = "correct" if from_passage and numbers_ok else "wrong"
            if question_language(result.answer) != question["lang"]:
                for group in (question["category"], "all"):
                    groups[group]["other language"] += 1
        for group in {question["category"], "all" if question["category"] != "permission" else "permission"}:
            groups[group][outcome] += 1
            groups[group]["n"] += 1
        if question["category"] != "permission":
            answers.append(
                {
                    "query": question["query"],
                    "category": question["category"],
                    "outcome": outcome,
                    "answer": result.answer,
                    "issues": result.issues,
                }
            )
    # To read: the answers that were not correct first, then a few correct.
    misses = [a for a in answers if a["outcome"] != "correct"]
    samples = misses[:8] + [a for a in answers if a["outcome"] == "correct"][: max(2, 8 - len(misses))]
    return {
        "groups": {g: dict(v) for g, v in sorted(groups.items())},
        "leaks": leaks,
        "mixed_abstain": mixed,
        "questions": len(questions),
        "latency_ms": round(1000 * sum(times) / len(times), 1) if times else 0.0,
        "p95_ms": round(1000 * sorted(times)[int(0.95 * (len(times) - 1))], 1) if times else 0.0,
        "samples": samples,
        "answers": answers,
    }


def format_answer_report(result: dict) -> str:
    columns = ("correct", "wrong", "abstained", "unverified", "answered", "other language")
    lines = ["Answers per question group (counts); leaks must be 0", ""]
    header = f"{'group':<12}{'n':>5}" + "".join(f"{c:>15}" for c in columns)
    lines += [header, "-" * len(header)]
    for group, counts in result["groups"].items():
        lines.append(
            f"{group:<12}{counts['n']:>5}" + "".join(f"{counts.get(c, 0):>15}" for c in columns)
        )
    lines.append("-" * len(header))
    lines.append(
        f"leaks {result['leaks']}   NAO_SEI mixed into answers {result['mixed_abstain']}   "
        f"average {result['latency_ms']} ms   p95 {result['p95_ms']} ms"
    )
    return "\n".join(lines)
