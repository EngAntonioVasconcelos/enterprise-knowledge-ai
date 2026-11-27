import pytest

from app.services import embeddings, llm, reranking
from app.services.answer_service import answer_question
from tests.integration import test_document_permissions as permissions
from tests.integration.answer_harness import evaluate_answers, format_answer_report
from tests.integration.retrieval_harness import ingest, load_dataset


pytestmark = pytest.mark.integration

perm_db = permissions.perm_db


@pytest.fixture
def stand_ins(monkeypatch):
    for module in (embeddings, reranking, llm):
        module._cached.cache_clear()
    monkeypatch.setattr(embeddings.settings, "EMBEDDING_PROVIDER", "hashing")
    monkeypatch.setattr(reranking.settings, "RERANK_PROVIDER", "overlap")
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "extractive")
    yield
    for module in (embeddings, reranking, llm):
        module._cached.cache_clear()


@pytest.fixture
def library(perm_db, stand_ins, tmp_path):
    world = permissions.World(perm_db)
    dataset = load_dataset()
    ingest(perm_db, world, dataset, tmp_path)
    return world, dataset


def test_an_answer_cites_the_passage_it_comes_from(perm_db, library):
    world, _ = library
    permissions._as_runtime(perm_db, world.rui)

    result = answer_question(
        perm_db, organization_id=world.organization, question="per diem for meals when travelling"
    )

    assert not result.abstained and result.verified
    assert "50 euros" in result.answer and result.cited
    cited = [s for s in result.sources if s.number in result.cited]
    assert cited[0].hit.title == "Travel and Expense Policy"


def test_confidential_documents_never_reach_the_answer(perm_db, library):
    world, _ = library
    permissions._as_runtime(perm_db, world.rui)

    result = answer_question(
        perm_db, organization_id=world.organization, question="banda salarial E3 centro de custo CC-4471"
    )

    assert all("confidencial" not in s.hit.title for s in result.sources)
    assert "2 800" not in result.answer and "CC-4471" not in result.answer


def test_the_answer_evaluation_runs_and_never_leaks(perm_db, library):
    world, dataset = library

    report = evaluate_answers(perm_db, world, dataset)
    print("\n" + format_answer_report(report))

    assert report["leaks"] == 0
    assert report["questions"] == len(dataset["questions"])
    groups = report["groups"]
    # The extractive stand-in copies sentences: with shared words it must
    # answer correctly, and it never produces an answer the checks refuse.
    assert groups["pt-words"].get("correct", 0) >= 4
    assert groups["exact-code"].get("correct", 0) >= 2
    assert groups["permission"]["n"] == 6
    assert groups["all"].get("unverified", 0) == 0


def test_the_held_out_questions_never_leak(perm_db, stand_ins, tmp_path):
    world = permissions.World(perm_db)
    dataset = load_dataset("holdout")
    ingest(perm_db, world, dataset, tmp_path)

    report = evaluate_answers(perm_db, world, dataset)
    print("\n" + format_answer_report(report))

    assert report["leaks"] == 0
    assert report["questions"] == len(dataset["questions"])
    # Questions no document answers are counted apart from the answerable ones.
    assert report["groups"]["no-answer"]["n"] == 6
    assert "no-answer" not in {a["category"] for a in report["answers"] if a["outcome"] == "correct"}
