import uuid

from pydantic import BaseModel, ConfigDict


class SearchHitResponse(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    title: str
    heading: str | None = None
    snippet: str
    start_char: int
    end_char: int
    score: float

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class SearchResponse(BaseModel):
    query: str
    results: list[SearchHitResponse]

    model_config = ConfigDict(extra="forbid")
