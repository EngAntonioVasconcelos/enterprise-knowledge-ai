import pytest

from app.services import embeddings
from tests.integration import test_document_permissions as permissions
from tests.integration.retrieval_harness import evaluate, format_report, ingest, load_dataset


pytestmark = pytest.mark.integration

perm_db = permissions.perm_db

# Floors measured with the hashing stand-in, which only knows shared words.
# They catch regressions in chunking, search by words, fusion and
# permissions. The real model is measured with scripts/evaluate_retrieval.py.
FLOORS = {
    ("keyword", "all"): 0.65,
    ("keyword", "pt-words"): 1.0,
    ("keyword", "en-words"): 0.8,
    ("keyword", "exact-code"): 1.0,
    ("hybrid", "all"): 0.65,
    ("hybrid", "pt-words"): 1.0,
    ("hybrid", "exact-code"): 1.0,
}


@pytest.fixture
def hashing(monkeypatch):
    embeddings._cached.cache_clear()
    monkeypatch.setattr(embeddings.settings, "EMBEDDING_PROVIDER", "hashing")
    yield
    embeddings._cached.cache_clear()


def test_retrieval_quality_does_not_regress(perm_db, hashing, tmp_path):
    db = perm_db
    world = permissions.World(db)
    dataset = load_dataset()
    assert ingest(db, world, dataset, tmp_path) > 0

    results = evaluate(db, world, dataset)
    print("\n" + format_report(results))

    for mode, result in results.items():
        assert result["available"], mode
        # The confidential documents never reach a member who cannot read them.
        assert result["leaks"] == 0, mode
    for (mode, group), floor in FLOORS.items():
        assert results[mode]["groups"][group]["recall_at_5"] >= floor, (mode, group)


def test_the_dataset_is_consistent():
    dataset = load_dataset()
    documents = dataset["documents"]
    assert len(dataset["questions"]) >= 40
    for question in dataset["questions"]:
        if question["category"] == "permission":
            assert all(documents[d]["restricted"] for d in question["expect_absent"])
        else:
            text = documents[question["expect_doc"]]["text"]
            assert question["expect_phrase"] in text, question["query"]
            assert not documents[question["expect_doc"]]["restricted"]
