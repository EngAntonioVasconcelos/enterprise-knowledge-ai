"""Search the passages a person may read (Phase 6, RAG Core).

Two searches, then one list:
- by words (PostgreSQL full text): exact terms, names, codes; accents and
  case are ignored;
- by meaning (vectors, pgvector): synonyms, paraphrases, another language;
- hybrid (default): both lists merged with Reciprocal Rank Fusion. Each
  passage scores 1 / (60 + its position) in every list it appears in; a
  passage near the top of both lists wins. Positions, not raw scores, are
  combined, because word scores and vector distances are not comparable.

Permissions are not checked here: the queries run as the person, and the
database returns only passages of documents they may open (row-level
security on documents, document_chunks and chunk_embeddings). Only the
current version of active documents is searched.

If vectors are unavailable (model not downloaded, disabled), hybrid search
falls back to words and says so in the result.
"""

import logging
import uuid
from dataclasses import dataclass, replace

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import InvalidInputError
from app.services.embeddings import (
    EmbeddingUnavailableError,
    get_embedder,
    vector_literal,
)


logger = logging.getLogger("eka.search")

MAX_QUERY_CHARS = 500
MAX_RESULTS = 50
SNIPPET_CHARS = 320
CANDIDATES = 40
RRF_K = 60
MODES = ("hybrid", "keyword", "semantic")


@dataclass(frozen=True)
class SearchHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    title: str
    heading: str | None
    snippet: str
    start_char: int
    end_char: int
    score: float
    keyword_rank: int | None = None
    semantic_rank: int | None = None


@dataclass(frozen=True)
class SearchResult:
    mode: str
    hits: list[SearchHit]
    note: str | None = None


COLUMNS = """
    c.id, c.document_id, c.version_id, d.title, c.heading, c.content,
    c.start_char, c.end_char
"""

KEYWORD_SQL = text(f"""
    SELECT {COLUMNS}, ts_rank_cd(c.content_tsv, q.query, 32) AS score
    FROM document_chunks AS c
    JOIN documents AS d
      ON d.id = c.document_id
     AND d.current_version_id = c.version_id
     AND d.status = 'active'
    CROSS JOIN (
        SELECT websearch_to_tsquery('simple', eka_search_text(:query)) AS query
    ) AS q
    WHERE c.organization_id = :organization_id
      AND c.content_tsv @@ q.query
    ORDER BY score DESC, c.document_id, c.ordinal
    LIMIT :limit
""")

# The cast to the model's size lets PostgreSQL use that model's HNSW index.
SEMANTIC_SQL = """
    SELECT {columns},
           1 - (e.embedding::vector({dims}) <=> CAST(:vector AS vector({dims}))) AS score
    FROM chunk_embeddings AS e
    JOIN document_chunks AS c ON c.id = e.chunk_id
    JOIN documents AS d
      ON d.id = c.document_id
     AND d.current_version_id = c.version_id
     AND d.status = 'active'
    WHERE e.model = :model
      AND e.organization_id = :organization_id
    ORDER BY e.embedding::vector({dims}) <=> CAST(:vector AS vector({dims}))
    LIMIT :limit
"""


def _snippet(content: str) -> str:
    content = " ".join(content.split())
    if len(content) <= SNIPPET_CHARS:
        return content
    cut = content.rfind(" ", 0, SNIPPET_CHARS)
    return content[: cut if cut > 0 else SNIPPET_CHARS] + "..."


def _hits(rows) -> list[SearchHit]:
    return [
        SearchHit(
            chunk_id=row[0],
            document_id=row[1],
            version_id=row[2],
            title=row[3],
            heading=row[4],
            snippet=_snippet(row[5]),
            start_char=row[6],
            end_char=row[7],
            score=float(row[8]),
        )
        for row in rows
    ]


def _clean(query: str, limit: int) -> tuple[str, int]:
    query = " ".join(query.split())
    if not query:
        raise InvalidInputError("The search is empty")
    if len(query) > MAX_QUERY_CHARS:
        raise InvalidInputError(f"The search is longer than {MAX_QUERY_CHARS} characters")
    return query, max(1, min(limit, MAX_RESULTS))


def keyword_search(
    db: Session, *, organization_id: uuid.UUID, query: str, limit: int
) -> list[SearchHit]:
    rows = db.execute(
        KEYWORD_SQL,
        {"query": query, "organization_id": organization_id, "limit": limit},
    ).all()
    return [replace(hit, keyword_rank=i + 1) for i, hit in enumerate(_hits(rows))]


def semantic_search(
    db: Session, *, organization_id: uuid.UUID, query: str, limit: int
) -> list[SearchHit]:
    embedder = get_embedder()
    vector = embedder.embed_query(query)
    # Row-level security filters after the index: keep scanning the index
    # until enough visible rows are found (pgvector 0.8 iterative scans).
    db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    rows = db.execute(
        text(SEMANTIC_SQL.format(columns=COLUMNS, dims=int(embedder.dims))),
        {
            "vector": vector_literal(vector),
            "model": embedder.model,
            "organization_id": organization_id,
            "limit": limit,
        },
    ).all()
    return [replace(hit, semantic_rank=i + 1) for i, hit in enumerate(_hits(rows))]


def fuse(keyword: list[SearchHit], semantic: list[SearchHit], limit: int) -> list[SearchHit]:
    """Reciprocal Rank Fusion of two ranked lists."""
    merged: dict[uuid.UUID, SearchHit] = {}
    scores: dict[uuid.UUID, float] = {}
    for hits, field in ((keyword, "keyword_rank"), (semantic, "semantic_rank")):
        for rank, hit in enumerate(hits, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (RRF_K + rank)
            current = merged.get(hit.chunk_id, hit)
            merged[hit.chunk_id] = replace(current, **{field: rank})
    ordered = sorted(merged, key=lambda chunk_id: (-scores[chunk_id], str(chunk_id)))
    return [replace(merged[c], score=round(scores[c], 6)) for c in ordered[:limit]]


def search(
    db: Session,
    *,
    organization_id: uuid.UUID,
    query: str,
    limit: int = 20,
    mode: str = "hybrid",
) -> SearchResult:
    if mode not in MODES:
        raise InvalidInputError(f"mode must be one of: {', '.join(MODES)}")
    query, limit = _clean(query, limit)

    if mode == "keyword":
        return SearchResult(
            "keyword",
            keyword_search(db, organization_id=organization_id, query=query, limit=limit),
        )

    try:
        semantic = semantic_search(
            db,
            organization_id=organization_id,
            query=query,
            limit=limit if mode == "semantic" else CANDIDATES,
        )
    except EmbeddingUnavailableError as exc:
        if mode == "semantic":
            raise InvalidInputError(f"Search by meaning is unavailable: {exc}") from None
        logger.warning("search by meaning unavailable: %s", exc)
        return SearchResult(
            "keyword",
            keyword_search(db, organization_id=organization_id, query=query, limit=limit),
            note="Search by meaning is unavailable; results use words only.",
        )

    if mode == "semantic":
        return SearchResult("semantic", semantic)
    keyword = keyword_search(
        db, organization_id=organization_id, query=query, limit=CANDIDATES
    )
    return SearchResult("hybrid", fuse(keyword, semantic, limit))


def search_text(
    db: Session, *, organization_id: uuid.UUID, query: str, limit: int = 20
) -> list[SearchHit]:
    """Search by words only (the first version's entry point)."""
    query, limit = _clean(query, limit)
    return keyword_search(db, organization_id=organization_id, query=query, limit=limit)
