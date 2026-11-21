import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.services.answer_service import MAX_PREVIOUS_QUESTIONS, MAX_QUESTION_CHARS


class AnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    # The language of the interface: used only when the question itself
    # does not show its language ("minimum password length").
    interface_language: Literal["pt", "en", "fr"] | None = None
    # The person's own earlier questions in this conversation, oldest
    # first: they make follow-ups ("and for interns?") work. Never answers.
    previous_questions: list[
        Annotated[str, StringConstraints(min_length=1, max_length=MAX_QUESTION_CHARS)]
    ] = Field(default_factory=list, max_length=MAX_PREVIOUS_QUESTIONS)

    model_config = ConfigDict(extra="forbid")


class AnswerSourceResponse(BaseModel):
    # The number the answer uses to cite it: [1], [2]...
    number: int
    cited: bool
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    title: str
    heading: str | None = None
    snippet: str
    start_char: int
    end_char: int

    model_config = ConfigDict(extra="forbid")


class AnswerDataResponse(BaseModel):
    """The database rows an answer comes from (AL-4), cited as [D1]."""

    connection_id: uuid.UUID
    connection_name: str
    # The read-only query that ran, so the person can check it.
    sql: str
    columns: list[str]
    rows: list[list[str | int | float | bool | None]]
    truncated: bool

    model_config = ConfigDict(extra="forbid")


class AnswerResponse(BaseModel):
    question: str
    answer: str
    # True when the sources did not answer, or the answer failed the checks.
    abstained: bool
    verified: bool
    sources: list[AnswerSourceResponse]
    prompt_id: str
    model: str | None = None
    # pt, en or fr: the language the answer is written in.
    language: str
    note: str | None = None
    timings_ms: dict[str, float]
    # Present when the answer comes from a database, not from documents.
    data: AnswerDataResponse | None = None

    model_config = ConfigDict(extra="forbid")
