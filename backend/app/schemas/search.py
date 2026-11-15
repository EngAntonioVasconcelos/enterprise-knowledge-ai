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
    # Share of the question's meaningful words in the passage (0 to 1).
    coverage: float | None = None
    # The passage contains a code or number of the question.
    code_match: bool = False
    # Near copies of this passage (other sites, file copies) shown further down.
    similar: int = 0
    # The reranker's score when the results were reranked (higher is better).
    rerank_score: float | None = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class SearchResponse(BaseModel):
    query: str
    mode: str
    note: str | None = None
    reranked: bool = False
    results: list[SearchHitResponse]

    model_config = ConfigDict(extra="forbid")
