"""The embedding gateway: one place that turns text into vectors.

An embedding is a list of numbers (here 384) that places a text on a map
of meanings: texts that mean similar things get close vectors, even with
different words or in another language. Search by meaning compares the
question's vector with the passages' vectors.

Every vector is stored with the name of the model that made it, because
vectors from different models are not comparable. Changing model means
computing new vectors next to the old ones, never mixing them
(Model Agnostic, Phase 6).

Providers (setting EMBEDDING_PROVIDER):
- fastembed: intfloat/multilingual-e5-small, run locally on the CPU with
  ONNX Runtime; free, private (texts never leave the machine), 100+
  languages. The model files (about 470 MB) are downloaded once by
  scripts/try_embeddings.py; the API and the worker never download.
- hashing: a tiny deterministic stand-in for tests and CI. It only knows
  shared words, not meaning.
- none: no vectors; search falls back to words only.
"""

import hashlib
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import settings


E5_MODEL = "intfloat/multilingual-e5-small"
E5_DIMS = 384
HASHING_MODEL = "test/hashing-384"


class EmbeddingUnavailableError(RuntimeError):
    """No model can embed right now (not downloaded, disabled, failed)."""


class Embedder(Protocol):
    model: str
    dims: int

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class HashingEmbedder:
    """Words hashed into 384 buckets; deterministic, no download."""

    model = HASHING_MODEL
    dims = 384
    WORD = re.compile(r"\w+", re.UNICODE)

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dims
        for word in self.WORD.findall(text.lower()):
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dims
            vector[index] += 1.0 if digest[4] % 2 else -1.0
        return _normalize(vector)

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FastEmbedE5:
    """multilingual-e5-small through fastembed (ONNX Runtime, CPU)."""

    model = E5_MODEL
    dims = E5_DIMS

    def __init__(self, cache_dir: str, *, allow_download: bool = False):
        try:
            from fastembed import TextEmbedding
            from fastembed.common.model_description import ModelSource, PoolingType
        except ImportError as exc:
            raise EmbeddingUnavailableError("fastembed is not installed") from exc

        if E5_MODEL not in {m["model"] for m in TextEmbedding.list_supported_models()}:
            TextEmbedding.add_custom_model(
                model=E5_MODEL,
                pooling=PoolingType.MEAN,
                normalization=True,
                sources=ModelSource(hf=E5_MODEL),
                dim=E5_DIMS,
                model_file="onnx/model.onnx",
            )
        try:
            self._model = TextEmbedding(
                model_name=E5_MODEL,
                cache_dir=cache_dir,
                local_files_only=not allow_download,
            )
        except Exception as exc:
            raise EmbeddingUnavailableError(
                "the embedding model is not available locally; run "
                "python -m scripts.try_embeddings to download it once "
                f"({type(exc).__name__})"
            ) from None

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts, batch_size=32)]

    # e5 models were trained with these prefixes; without them quality drops.
    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._embed([f"passage: {text}" for text in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._embed([f"query: {text}"])[0]


@lru_cache(maxsize=1)
def _cached(provider: str, cache_dir: str) -> Embedder:
    if provider == "fastembed":
        return FastEmbedE5(cache_dir)
    if provider == "hashing":
        return HashingEmbedder()
    raise EmbeddingUnavailableError(f"embeddings are disabled (provider {provider})")


def get_embedder() -> Embedder:
    """The configured embedder, loaded once per process."""
    cache_dir = str(Path(settings.EMBEDDING_CACHE_DIR).resolve())
    return _cached(settings.EMBEDDING_PROVIDER, cache_dir)


def embeddings_enabled() -> bool:
    return settings.EMBEDDING_PROVIDER != "none"


def vector_literal(vector: list[float]) -> str:
    """The text form pgvector accepts: [0.1,0.2,...]."""
    return "[" + ",".join(f"{v:.7g}" for v in vector) + "]"
