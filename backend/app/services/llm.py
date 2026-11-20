"""The language model gateway: one place that sends prompts to a model.

The answer step (answer_service) never talks to a provider directly: it
asks get_chat_model() for the configured model and calls complete(). Changing
provider or model is a setting, not a code change (Model Agnostic).

Providers (setting LLM_PROVIDER):
- openai_compatible: any server that speaks the OpenAI chat completions
  format: hosted providers, and local servers such as Ollama
  (LLM_BASE_URL=http://localhost:11434/v1) or LM Studio. Needs
  LLM_BASE_URL and LLM_MODEL; LLM_API_KEY only if the server asks for one.
  With a hosted provider the question and the passages leave our servers:
  that is the organization's choice to make.
- extractive: a deterministic stand-in for tests and CI. It picks the
  source sentence that shares the most words with the question and cites
  it; it does not write or understand anything.
- none (default): no model; the answer step says it is unavailable.
"""

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import httpx

from app.core.config import settings


EXTRACTIVE_MODEL = "test/extractive"
ABSTAIN = "NAO_SEI"


class LLMUnavailableError(RuntimeError):
    """No model can answer right now (not configured, unreachable, failed)."""


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class ChatModel(Protocol):
    model: str

    def complete(self, system: str, user: str, *, max_tokens: int) -> Completion: ...


class OpenAICompatible:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
        seed: int | None = None,
    ):
        self.model = model
        self.seed = seed
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    def complete(self, system: str, user: str, *, max_tokens: int) -> Completion:
        try:
            response = self._client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    # 0: the same question and sources give the same answer.
                    "temperature": 0,
                    "max_tokens": max_tokens,
                    # A fixed seed makes local models repeatable on a CPU,
                    # where temperature 0 alone is not enough (AJ-1b).
                    **({"seed": self.seed} if self.seed is not None else {}),
                },
            )
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(
                f"the language model could not be reached ({type(exc).__name__})"
            ) from None
        if response.status_code != 200:
            # The body may echo the request; only the status is reported.
            raise LLMUnavailableError(
                f"the language model answered with status {response.status_code}"
            )
        try:
            body = response.json()
            text = body["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMUnavailableError("the language model sent an unreadable answer") from None
        usage = body.get("usage") or {}
        return Completion(
            text=text,
            model=body.get("model") or self.model,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )


SOURCE = re.compile(r'<source id="(\d+)"[^>]*>\n(.*?)\n</source>', re.DOTALL)
QUESTION = re.compile(r"^Question: (.*)$", re.MULTILINE)


def _words(value: str) -> set[str]:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return {w for w in re.findall(r"[0-9a-z]+", plain) if len(w) > 2}


class ExtractiveModel:
    """Copies the best matching source sentence and cites it; tests only."""

    model = EXTRACTIVE_MODEL

    def complete(self, system: str, user: str, *, max_tokens: int) -> Completion:
        match = QUESTION.search(user)
        asked = _words(match.group(1)) if match else set()
        best, best_score = None, 1
        for number, content in SOURCE.findall(user):
            for sentence in re.split(r"(?<=[.!?])\s+", content):
                score = len(asked & _words(sentence))
                if score > best_score:
                    best, best_score = f"{sentence.strip()} [{number}]", score
        return Completion(text=best or ABSTAIN, model=self.model)


@lru_cache(maxsize=1)
def _cached(
    provider: str, base_url: str | None, model: str | None, timeout: float
) -> ChatModel:
    if provider == "openai_compatible":
        if not base_url or not model:
            raise LLMUnavailableError("set LLM_BASE_URL and LLM_MODEL to use a language model")
        return OpenAICompatible(
            base_url, model, settings.LLM_API_KEY, timeout, seed=settings.LLM_SEED
        )
    if provider == "extractive":
        return ExtractiveModel()
    raise LLMUnavailableError(f"no language model is configured (provider {provider})")


def get_chat_model() -> ChatModel:
    """The configured model, created once per process."""
    return _cached(
        settings.LLM_PROVIDER,
        settings.LLM_BASE_URL,
        settings.LLM_MODEL,
        settings.LLM_TIMEOUT_SECONDS,
    )
