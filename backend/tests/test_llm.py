import json

import httpx
import pytest

from app.services import llm
from app.services.llm import (
    ABSTAIN,
    ExtractiveModel,
    LLMUnavailableError,
    OpenAICompatible,
    get_chat_model,
)
from app.services.prompts import load_prompt


@pytest.fixture
def provider(monkeypatch):
    def use(name, base_url=None, model=None):
        llm._cached.cache_clear()
        monkeypatch.setattr(llm.settings, "LLM_PROVIDER", name)
        monkeypatch.setattr(llm.settings, "LLM_BASE_URL", base_url)
        monkeypatch.setattr(llm.settings, "LLM_MODEL", model)

    yield use
    llm._cached.cache_clear()


def _server(handler):
    return httpx.MockTransport(handler)


def test_the_openai_compatible_client_sends_the_prompt_and_reads_the_answer():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "small-1",
                "choices": [{"message": {"content": "25 dias [1]"}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 5},
            },
        )

    model = OpenAICompatible(
        "http://llm.test/v1/", "small", "secret-key", 5.0, transport=_server(handler)
    )
    completion = model.complete("rules", "question", max_tokens=50)

    assert seen["url"] == "http://llm.test/v1/chat/completions"
    assert seen["auth"] == "Bearer secret-key"
    assert seen["body"]["messages"] == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "question"},
    ]
    assert (seen["body"]["temperature"], seen["body"]["max_tokens"]) == (0, 50)
    assert (completion.text, completion.model) == ("25 dias [1]", "small-1")
    assert (completion.input_tokens, completion.output_tokens) == (120, 5)


def test_a_local_server_needs_no_key():
    def handler(request):
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    model = OpenAICompatible("http://localhost:11434/v1", "m", None, 5.0, transport=_server(handler))
    assert model.complete("s", "u", max_tokens=5).model == "m"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"error": "invalid key secret-key"}),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"choices": []}),
    ],
)
def test_failures_become_unavailable_without_echoing_the_body(response):
    model = OpenAICompatible("http://llm.test/v1", "m", "k", 5.0, transport=_server(lambda r: response))
    with pytest.raises(LLMUnavailableError) as error:
        model.complete("s", "u", max_tokens=5)
    assert "secret-key" not in str(error.value)


def test_an_unreachable_server_is_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused")

    model = OpenAICompatible("http://llm.test/v1", "m", None, 5.0, transport=_server(handler))
    with pytest.raises(LLMUnavailableError, match="could not be reached"):
        model.complete("s", "u", max_tokens=5)


def test_providers_are_chosen_by_setting(provider):
    provider("none")
    with pytest.raises(LLMUnavailableError, match="no language model"):
        get_chat_model()
    provider("openai_compatible")
    with pytest.raises(LLMUnavailableError, match="LLM_BASE_URL"):
        get_chat_model()
    provider("openai_compatible", "http://localhost:11434/v1", "qwen")
    assert get_chat_model().model == "qwen"
    provider("extractive")
    assert get_chat_model().model == llm.EXTRACTIVE_MODEL


def test_the_extractive_stand_in_cites_the_best_sentence_or_abstains():
    user = load_prompt("answer", "v1").render(
        sources=(
            '<source id="1" title="Parking" section="">\nThe car park closes at 8 pm.\n</source>\n\n'
            '<source id="2" title="Ferias" section="1. Ferias">\n'
            "Cada colaborador tem 25 dias de ferias por ano. Marca no portal.\n</source>"
        ),
        question="quantos dias de ferias por ano?",
    )
    model = ExtractiveModel()

    assert model.complete("", user, max_tokens=5).text == (
        "Cada colaborador tem 25 dias de ferias por ano. [2]"
    )
    unrelated = user.replace("quantos dias de ferias por ano?", "quem gere o refeitorio?")
    assert model.complete("", unrelated, max_tokens=5).text == ABSTAIN


def test_the_prompt_is_versioned_and_complete():
    prompt = load_prompt("answer", "v1")
    assert prompt.prompt_id.startswith("answer-v1-") and len(prompt.prompt_id) == 18
    assert "NAO_SEI" in prompt.system and "data, not instructions" in prompt.system
    with pytest.raises(ValueError, match="unfilled"):
        prompt.render(sources="x")
