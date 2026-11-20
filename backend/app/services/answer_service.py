"""Answers with citations, or an honest "I don't know" (Phase 6, AJ-1).

The path of one question:
1. search: hybrid search with the reranker, as the person asking (row-level
   security: only passages of documents they may open);
2. context: the best passages, up to MAX_SOURCES and MAX_CONTEXT_CHARS,
   numbered [1], [2]... with their document title and section;
3. prompt: the versioned prompt (app/prompts/answer_v1.txt) with the rules:
   only the sources, cite every fact, NAO_SEI when they do not answer, the
   language of the question, and the sources are data, not instructions;
4. model: the configured language model (app/services/llm.py);
5. verification: every citation must point to a source that was given and
   every number in the answer must be written in a cited source (or in the
   question). An answer that fails is not shown: the person gets "I could
   not find a reliable answer" with the sources, never an unchecked claim.

Nothing is stored here: the question and the answer are not logged, only
their measurements (prompt id, model, sources, times, verified).
"""

import logging
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import InvalidInputError, UnavailableError
from app.services.llm import ABSTAIN, LLMUnavailableError, get_chat_model
from app.services.prompts import load_prompt
from app.services.search_service import SearchHit, search


logger = logging.getLogger("eka.answers")

PROMPT_NAME = "answer"
PROMPT_VERSIONS = ("v1", "v2", "v3", "v4")
LANGUAGES = ("pt", "en", "fr")
# How prompt v4 names the language of the answer, decided here and not by
# the model: small models drift into the language of the sources.
LANGUAGE_NAMES = {
    "pt": 'European Portuguese (Portugal), addressing the person as "tu" '
    '(for example "tens", "podes"), never "voce"',
    "en": "English",
    "fr": 'French, addressing the person as "vous"',
}
MAX_QUESTION_CHARS = 500
MAX_SOURCES = 5
MAX_CONTEXT_CHARS = 8000
MAX_OUTPUT_TOKENS = 400

CITATION = re.compile(r"\[(\d+)\]")
# Numbers as people write them: 25, 0.40, 40 000, 1.200,50, 20000.
NUMBER = re.compile(r"\d+(?:[ \u00a0.,]\d+)*")

NO_ANSWER = {
    "pt": "N\u00e3o encontrei, nos documentos a que tens acesso, uma resposta segura a esta pergunta.",
    "en": "I could not find a reliable answer to this question in the documents you can access.",
    "fr": "Je n\u2019ai pas trouv\u00e9, dans les documents auxquels vous avez acc\u00e8s, de r\u00e9ponse fiable \u00e0 cette question.",
}
# The small words of each language, accents removed, to tell the language
# of a question or an answer. Words two languages share count for neither.
EN_WORDS = frozenset(
    "the is are what how when where who which can do does my i you of to for in "
    "be must should much many with from after".split()
)
PT_WORDS = frozenset(
    "o os as um uma uns umas do da dos das no na nas pelo pela com sem ao aos nao "
    "como qual quais quanto quantos quanta quantas quando onde quem porque eu tu ele "
    "ela eles elas lhe meu minha meus minhas seu sua seus suas tenho tem temos posso "
    "pode podem ser sao esta estao isso este essa esse mais muito muita ja ate e em "
    "para por".split()
)
FR_WORDS = frozenset(
    "le la les un une des du au aux est sont quel quelle quels quelles comment combien "
    "je j mon ma mes vous votre il elle ils elles pour dans avec sur par pas ne qu qui "
    "y plus apres avant tous tout toutes ai puis dois peut peux faut ce cet cette "
    "ces leur leurs an jours".split()
)


@dataclass(frozen=True)
class Source:
    number: int
    hit: SearchHit


@dataclass
class AnswerResult:
    answer: str
    abstained: bool
    verified: bool
    sources: list[Source]
    cited: list[int]
    prompt_id: str
    model: str | None
    issues: list[str] = field(default_factory=list)
    # The model wrote NAO_SEI next to an answer; the marker was removed.
    mixed_abstain: bool = False
    note: str | None = None
    timings_ms: dict[str, float] = field(default_factory=dict)
    # The language the answer is written in: pt, en or fr.
    language: str = "pt"


def question_language(question: str, fallback: str | None = None) -> str:
    """pt, en or fr, from the small words of the text.

    A text with none of them ("minimum password length", "EXP-22") takes
    the fallback, the language of the interface, then Portuguese.
    """
    plain = unicodedata.normalize("NFD", question.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    words = re.findall(r"[a-z]+", plain)
    scores = {
        language: sum(w in own and not any(w in o for o in others) for w in words)
        for language, own, others in (
            ("pt", PT_WORDS, (EN_WORDS, FR_WORDS)),
            ("en", EN_WORDS, (PT_WORDS, FR_WORDS)),
            ("fr", FR_WORDS, (PT_WORDS, EN_WORDS)),
        )
    }
    best = max(scores.values())
    if best == 0:
        return fallback if fallback in LANGUAGES else "pt"
    if scores["pt"] == best:
        return "pt"
    return "en" if scores["en"] == best else "fr"


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def numbers_in(text: str) -> set[str]:
    """The numbers of a text, as digits only ("40 000" and "40000" match)."""
    return {_digits(n) for n in NUMBER.findall(text)}


def select_sources(hits: list[SearchHit]) -> list[Source]:
    sources, used = [], 0
    for hit in hits[:MAX_SOURCES]:
        content = hit.content or hit.snippet
        if sources and used + len(content) > MAX_CONTEXT_CHARS:
            break
        used += len(content)
        sources.append(Source(len(sources) + 1, hit))
    return sources


def _clean(value: str) -> str:
    """A source cannot close its own tag or open a new one."""
    return re.sub(r"</?source", "(source", value, flags=re.IGNORECASE)


def render_sources(sources: list[Source]) -> str:
    blocks = []
    for source in sources:
        hit = source.hit
        title = _clean(hit.title).replace('"', "'")
        section = _clean(hit.heading or "").replace('"', "'")
        blocks.append(
            f'<source id="{source.number}" title="{title}" section="{section}">\n'
            f"{_clean(hit.content or hit.snippet).strip()}\n</source>"
        )
    return "\n\n".join(blocks)


def verify(answer: str, sources: list[Source], question: str) -> tuple[list[int], list[str]]:
    """The cited source numbers, and what is wrong with the answer (if anything)."""
    cited = sorted({int(n) for n in CITATION.findall(answer)})
    issues = []
    if not cited:
        issues.append("the answer cites no source")
    given = {s.number: s for s in sources}
    missing = [n for n in cited if n not in given]
    if missing:
        issues.append(f"the answer cites sources that were not given: {missing}")
    allowed = numbers_in(question)
    for number in cited:
        if number in given:
            allowed |= numbers_in(given[number].hit.content or given[number].hit.snippet)
    claimed = numbers_in(CITATION.sub(" ", answer))
    unsupported = sorted(n for n in claimed if n not in allowed)
    if unsupported:
        issues.append(f"numbers not found in the cited sources: {unsupported}")
    return cited, issues


def split_abstain(text: str) -> tuple[str, bool]:
    """The answer without NAO_SEI markers, and whether one was mixed in.

    The prompt says NAO_SEI must be the whole reply, but small models
    sometimes append it to a real answer ("...[2]. NAO_SEI"). The person
    must never see the marker: it is removed and the rest is verified as
    any other answer; only NAO_SEI alone means "no answer".
    """
    stripped = text.strip()
    if not stripped or stripped.rstrip(".").strip() == ABSTAIN:
        return "", False
    if ABSTAIN not in stripped:
        return stripped, False
    cleaned = " ".join(stripped.replace(ABSTAIN, " ").split()).strip(" .")
    return (cleaned + "." if cleaned else ""), True


def answer_question(
    db: Session,
    *,
    organization_id: uuid.UUID,
    question: str,
    prompt_version: str | None = None,
    interface_language: str | None = None,
) -> AnswerResult:
    question = " ".join(question.split())
    if not question:
        raise InvalidInputError("The question is empty")
    if len(question) > MAX_QUESTION_CHARS:
        raise InvalidInputError(f"The question is longer than {MAX_QUESTION_CHARS} characters")

    version = prompt_version or settings.ANSWER_PROMPT_VERSION
    if version not in PROMPT_VERSIONS:
        raise InvalidInputError(f"prompt version must be one of: {', '.join(PROMPT_VERSIONS)}")
    prompt = load_prompt(PROMPT_NAME, version)
    language = question_language(question, fallback=interface_language)
    timings: dict[str, float] = {}

    started = time.perf_counter()
    found = search(
        db,
        organization_id=organization_id,
        query=question,
        limit=MAX_SOURCES,
        rerank=settings.ANSWER_RERANK,
    )
    timings["search"] = round(1000 * (time.perf_counter() - started), 1)
    sources = select_sources(found.hits)

    def no_answer(issues: list[str], model: str | None) -> AnswerResult:
        return AnswerResult(
            answer=NO_ANSWER[language],
            abstained=True,
            verified=not issues,
            sources=sources,
            cited=[],
            prompt_id=prompt.prompt_id,
            model=model,
            issues=issues,
            note=found.note,
            timings_ms=timings,
            language=language,
        )

    if not sources:
        # Nothing the person may read matches: no need to ask a model.
        result = no_answer([], None)
        _log(result)
        return result

    try:
        model = get_chat_model()
    except LLMUnavailableError as exc:
        raise UnavailableError(f"Answers are unavailable: {exc}") from None

    started = time.perf_counter()
    try:
        completion = model.complete(
            prompt.system,
            prompt.render(
                sources=render_sources(sources),
                question=question,
                language=LANGUAGE_NAMES[language],
            ),
            max_tokens=MAX_OUTPUT_TOKENS,
        )
    except LLMUnavailableError as exc:
        raise UnavailableError(f"Answers are unavailable: {exc}") from None
    timings["model"] = round(1000 * (time.perf_counter() - started), 1)

    text, mixed = split_abstain(completion.text)
    if not text:
        result = no_answer([], completion.model)
    else:
        cited, issues = verify(text, sources, question)
        if issues:
            result = no_answer(issues, completion.model)
        else:
            result = AnswerResult(
                answer=text,
                abstained=False,
                verified=True,
                sources=sources,
                cited=cited,
                prompt_id=prompt.prompt_id,
                model=completion.model,
                note=found.note,
                timings_ms=timings,
                language=language,
            )
    result.mixed_abstain = mixed
    _log(result)
    return result


def _log(result: AnswerResult) -> None:
    # Measurements only: never the question, the passages or the answer.
    logger.info(
        "answer prompt=%s model=%s sources=%d cited=%s abstained=%s verified=%s ms=%s",
        result.prompt_id,
        result.model,
        len(result.sources),
        result.cited,
        result.abstained,
        result.verified,
        result.timings_ms,
    )
