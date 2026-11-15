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
    # Position in each list (1 = first); None when the passage was not in it.
    keyword_rank: int | None = None
    semantic_rank: int | None = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class SearchResponse(BaseModel):
    query: str
    mode: str
    note: str | None = None
    results: list[SearchHitResponse]

    model_config = ConfigDict(extra="forbid")
