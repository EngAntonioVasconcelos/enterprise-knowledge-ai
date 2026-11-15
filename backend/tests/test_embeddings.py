import math
import uuid

import pytest

from app.services import embeddings
from app.services.embeddings import (
    HashingEmbedder,
    EmbeddingUnavailableError,
    get_embedder,
    vector_literal,
)
from app.services.search_service import SearchHit, fuse


def _hit(name, **ranks):
    return SearchHit(
        chunk_id=uuid.uuid5(uuid.NAMESPACE_DNS, name),
        document_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        title=name,
        heading=None,
        snippet=name,
        start_char=0,
        end_char=1,
        score=0.0,
        **ranks,
    )


def test_hashing_vectors_are_deterministic_and_normalized():
    embedder = HashingEmbedder()
    [a, b] = embedder.embed_passages(["dias de ferias", "dias de ferias"])

    assert a == b and len(a) == 384
    assert math.isclose(sum(v * v for v in a), 1.0, rel_tol=1e-9)


def test_shared_words_bring_hashing_vectors_closer():
    embedder = HashingEmbedder()
    query = embedder.embed_query("dias de ferias")
    near, far = embedder.embed_passages(["25 dias de ferias por ano", "parking closes at 8"])

    def cosine(x, y):
        return sum(p * q for p, q in zip(x, y))

    assert cosine(query, near) > cosine(query, far)


def test_vectors_are_written_as_pgvector_text():
    assert vector_literal([0.5, -1.0, 1e-9]) == "[0.5,-1,1e-09]"


def test_disabled_embeddings_are_reported(monkeypatch):
    embeddings._cached.cache_clear()
    monkeypatch.setattr(embeddings.settings, "EMBEDDING_PROVIDER", "none")
    try:
        with pytest.raises(EmbeddingUnavailableError):
            get_embedder()
    finally:
        embeddings._cached.cache_clear()


def test_e5_gets_its_prefixes(monkeypatch):
    seen = []

    class Model:
        def embed(self, texts, batch_size):
            seen.extend(texts)
            return [type("V", (), {"tolist": lambda self: [1.0, 0.0]})() for _ in texts]

    e5 = embeddings.FastEmbedE5.__new__(embeddings.FastEmbedE5)
    e5._model = Model()
    e5.embed_passages(["Ferias: 25 dias."])
    e5.embed_query("quantos dias?")

    assert seen == ["passage: Ferias: 25 dias.", "query: quantos dias?"]


def test_fusion_rewards_passages_found_by_both_searches():
    keyword = [_hit("a"), _hit("b"), _hit("c")]
    semantic = [_hit("c"), _hit("d"), _hit("a")]

    fused = fuse(keyword, semantic, limit=10)

    assert [h.title for h in fused][:2] == ["a", "c"]
    first = fused[0]
    assert (first.keyword_rank, first.semantic_rank) == (1, 3)
    assert {h.title for h in fused} == {"a", "b", "c", "d"}
    assert fused[-1].semantic_rank in (None, 2)
    assert len(fuse(keyword, semantic, limit=2)) == 2
