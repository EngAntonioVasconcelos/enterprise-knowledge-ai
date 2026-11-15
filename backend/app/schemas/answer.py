import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.services.answer_service import MAX_QUESTION_CHARS


class AnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)

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


class AnswerResponse(BaseModel):
    question: str
    answer: str
    # True when the sources did not answer, or the answer failed the checks.
    abstained: bool
    verified: bool
    sources: list[AnswerSourceResponse]
    prompt_id: str
    model: str | None = None
    note: str | None = None
    timings_ms: dict[str, float]

    model_config = ConfigDict(extra="forbid")
