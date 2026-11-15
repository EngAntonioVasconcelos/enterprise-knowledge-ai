"""The reranking gateway: a second, slower and smarter look at the results.

Search by words and by meaning are fast because they never read the
question and a passage together: words compare lists of terms, meaning
compares two vectors made separately. A cross-encoder (reranker) reads the
question next to each passage in one pass and scores how well that passage
answers it. That is too slow for the whole library, so it reorders only the
first RERANK_CANDIDATES results of the fast search.

It never sees passages the person may not read: it only reorders results
that row-level security already filtered.

Providers (setting RERANK_PROVIDER):
- fastembed: BAAI/bge-reranker-v2-m3 in its INT8 ONNX form (Apache 2.0,
  multilingual, about 570 MB), run locally on the CPU; free and private.
  Downloaded once by scripts/try_reranker.py; the API never downloads.
- overlap: a tiny deterministic stand-in for tests and CI (shared words).
- none: no reranking; results keep the search order.
"""

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import settings


RERANK_MODEL = "BAAI/bge-reranker-v2-m3-int8"
OVERLAP_MODEL = "test/overlap"
# How many of the first results the reranker reads. More finds more, but
# every extra passage adds time on the CPU (measured in AI-2).
RERANK_CANDIDATES = 20


class RerankUnavailableError(RuntimeError):
    """No reranker can run right now (not downloaded, disabled, failed)."""


class Reranker(Protocol):
    model: str

    def score(self, query: str, passages: list[str]) -> list[float]: ...


def _words(value: str) -> set[str]:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return set(re.findall(r"[0-9a-z]+", plain))


class OverlapReranker:
    """Share of the question's words found in the passage; tests only."""

    model = OVERLAP_MODEL

    def score(self, query: str, passages: list[str]) -> list[float]:
        asked = _words(query) or {""}
        return [len(asked & _words(p)) / len(asked) for p in passages]


class FastEmbedReranker:
    """bge-reranker-v2-m3 (INT8) through fastembed (ONNX Runtime, CPU)."""

    model = RERANK_MODEL

    def __init__(self, cache_dir: str, *, allow_download: bool = False):
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
        except ImportError as exc:
            raise RerankUnavailableError("fastembed is not installed") from exc
        try:
            self._model = TextCrossEncoder(
                model_name=RERANK_MODEL,
                cache_dir=cache_dir,
                local_files_only=not allow_download,
            )
        except Exception as exc:
            raise RerankUnavailableError(
                "the reranking model is not available locally; run "
                "python -m scripts.try_reranker to download it once "
                f"({type(exc).__name__})"
            ) from None

    def score(self, query: str, passages: list[str]) -> list[float]:
        return [float(s) for s in self._model.rerank(query, passages, batch_size=8)]


@lru_cache(maxsize=1)
def _cached(provider: str, cache_dir: str) -> Reranker:
    if provider == "fastembed":
        return FastEmbedReranker(cache_dir)
    if provider == "overlap":
        return OverlapReranker()
    raise RerankUnavailableError(f"reranking is disabled (provider {provider})")


def get_reranker() -> Reranker:
    """The configured reranker, loaded once per process."""
    cache_dir = str(Path(settings.EMBEDDING_CACHE_DIR).resolve())
    return _cached(settings.RERANK_PROVIDER, cache_dir)
