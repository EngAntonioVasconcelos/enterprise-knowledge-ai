import uuid
from dataclasses import replace

import pytest

from app.services import reranking, search_service
from app.services.reranking import (
    OverlapReranker,
    RerankUnavailableError,
    get_reranker,
)
from app.services.search_service import (
    SearchHit,
    SearchResult,
    fuse,
    rerank_hits,
    rerank_text,
)


def _hit(name, content="", **fields):
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
        content=content,
        **fields,
    )


@pytest.fixture
def provider(monkeypatch):
    def use(name):
        reranking._cached.cache_clear()
        monkeypatch.setattr(reranking.settings, "RERANK_PROVIDER", name)

    yield use
    reranking._cached.cache_clear()


def test_the_overlap_stand_in_scores_shared_words_without_accents():
    scores = OverlapReranker().score(
        "Dias de f\u00e9rias", ["25 dias de ferias", "parking", ""]
    )
    assert scores == [1.0, 0.0, 0.0]


def test_providers_are_chosen_by_setting(provider):
    provider("overlap")
    assert get_reranker().model == reranking.OVERLAP_MODEL
    provider("none")
    with pytest.raises(RerankUnavailableError):
        get_reranker()


def test_a_missing_model_is_reported_not_downloaded(provider, tmp_path, monkeypatch):
    monkeypatch.setattr(reranking.settings, "EMBEDDING_CACHE_DIR", str(tmp_path))
    provider("fastembed")
    with pytest.raises(RerankUnavailableError, match="try_reranker"):
        get_reranker()
    assert not any(tmp_path.iterdir())


def test_reranking_reorders_only_the_first_candidates(provider):
    provider("overlap")
    hits = [
        _hit("a", "nothing here"),
        _hit("b", "dias de ferias"),
        _hit("c", "dias"),
        _hit("d", "dias de ferias tambem"),
    ]

    ranked = rerank_hits("dias de ferias", hits, candidates=3)

    assert [h.title for h in ranked] == ["b", "c", "a", "d"]
    assert ranked[0].rerank_score == 1.0
    assert ranked[3].rerank_score is None


def test_equal_reranker_scores_keep_the_search_order(provider):
    provider("overlap")
    hits = [_hit("a", "x"), _hit("b", "y"), _hit("c", "z")]
    assert [h.title for h in rerank_hits("q", hits)] == ["a", "b", "c"]


def test_search_without_a_reranker_says_so_and_keeps_the_order(provider, monkeypatch):
    provider("none")
    hits = [_hit("a"), _hit("b")]
    monkeypatch.setattr(
        search_service, "_search", lambda *args: SearchResult("keyword", hits)
    )

    result = search_service.search(
        None, organization_id=uuid.uuid4(), query="q", limit=1, rerank=True
    )

    assert result.reranked is False
    assert [h.title for h in result.hits] == ["a"]
    assert "Reranking is unavailable" in result.note


def test_weighted_fusion_ignores_passages_that_share_too_little():
    right = _hit("right")
    junk = _hit("junk", coverage=0.25)
    keyword = [junk]
    semantic = [right] + [_hit(f"s{i}") for i in range(8)] + [junk]

    assert fuse(keyword, semantic, 10, "rrf")[0].title == "junk"
    weighted = fuse(keyword, semantic, 10, "weighted")
    assert weighted[0].title == "right"
    assert weighted[-1].title == "junk" and weighted[-1].keyword_rank is None


def test_weighted_fusion_keeps_strong_word_and_code_matches():
    strong = _hit("strong", coverage=1.0)
    code = _hit("code", coverage=0.5)
    fused = fuse([strong, code], [_hit("meaning"), code], 10, "weighted")

    assert fused[0].title == "code"
    assert fused[0].coverage == 0.5
    assert {h.title for h in fused} == {"code", "strong", "meaning"}


def test_an_unknown_fusion_is_refused():
    with pytest.raises(Exception, match="fusion must be one of"):
        search_service.search(None, organization_id=uuid.uuid4(), query="q", fusion="x")


def test_hits_built_without_measures_vote_fully():
    plain = replace(_hit("a"), coverage=None)
    assert fuse([plain], [], 10, "weighted")[0].title == "a"


def test_the_reranker_reads_where_the_passage_is_and_its_start():
    hit = replace(_hit("Manual", "um dois tres quatro"), heading="1. Ferias")

    assert rerank_text(hit, 0) == "Manual - 1. Ferias\num dois tres quatro"
    assert rerank_text(hit, 10) == "Manual - 1. Ferias\num dois"
    assert rerank_text(replace(hit, title="", heading=None), 3) == "um"


def test_search_asks_for_enough_candidates_and_uses_the_settings(provider, monkeypatch):
    provider("overlap")
    asked = {}

    def fake_search(db, organization_id, query, limit, mode, fusion):
        asked["limit"] = limit
        return SearchResult("hybrid", [_hit(f"h{i}", "q" if i == 4 else "x") for i in range(limit)])

    monkeypatch.setattr(search_service, "_search", fake_search)
    monkeypatch.setattr(search_service.settings, "RERANK_CANDIDATES", 5)

    result = search_service.search(
        None, organization_id=uuid.uuid4(), query="q", limit=2, rerank=True
    )

    assert asked["limit"] == 5
    assert result.reranked and [h.title for h in result.hits] == ["h4", "h0"]

    search_service.search(
        None, organization_id=uuid.uuid4(), query="q", limit=2, rerank=True,
        rerank_candidates=8,
    )
    assert asked["limit"] == 8
