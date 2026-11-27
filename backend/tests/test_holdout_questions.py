"""The held-out questions (Phase 9) stay usable and stay new.

They are only worth something if every expected passage exists, if none
of them repeats a question that prompts and search were tuned against,
and if the confidential documents they must never show are the
confidential ones.
"""

import json
import unicodedata
from pathlib import Path

EVALUATION = Path(__file__).resolve().parent / "evaluation"
CATEGORIES = {
    "pt-words", "pt-meaning", "en-words", "en-meaning", "en-to-pt", "pt-to-en",
    "fr-to-pt", "fr-to-en", "exact-code", "permission", "no-answer",
}


def _plain(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _load(name: str) -> dict:
    return json.loads((EVALUATION / name).read_text(encoding="ascii"))


def test_every_expected_passage_is_in_its_document():
    documents = _load("retrieval_dataset.json")["documents"]
    for question in _load("holdout_questions.json")["questions"]:
        assert question["category"] in CATEGORIES, question["query"]
        assert question["lang"] in {"pt", "en", "fr"}, question["query"]
        if question["category"] in ("permission", "no-answer"):
            assert question["expect_doc"] is None and question["expect_phrase"] is None
            continue
        text = _plain(documents[question["expect_doc"]]["text"])
        assert _plain(question["expect_phrase"]) in text, question["query"]


def test_no_held_out_question_repeats_a_tuned_one():
    tuned = {_plain(q["query"]) for q in _load("retrieval_dataset.json")["questions"]}
    held = [_plain(q["query"]) for q in _load("holdout_questions.json")["questions"]]
    assert len(held) == len(set(held))
    assert not tuned & set(held)


def test_what_must_never_show_is_confidential():
    documents = _load("retrieval_dataset.json")["documents"]
    questions = _load("holdout_questions.json")["questions"]
    for question in questions:
        for name in question["expect_absent"] or []:
            assert documents[name]["restricted"], question["query"]
    assert all(q["expect_absent"] for q in questions if q["category"] == "permission")
    assert sum(q["category"] == "no-answer" for q in questions) >= 5
