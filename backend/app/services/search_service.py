"""Search the passages a person may read (Phase 6, RAG Core).

This step searches by words (PostgreSQL full text): exact terms, names and
codes are found, accents and case are ignored. Meaning-based search
(vectors) joins it in the next step to make the search hybrid.

Permissions are not checked here: the query runs as the person, and the
database only returns passages of documents they may open (row-level
security on document_chunks and documents). Only the current version of
active documents is searched.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import InvalidInputError


MAX_QUERY_CHARS = 500
MAX_RESULTS = 50
SNIPPET_CHARS = 320


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


SEARCH_SQL = text("""
    SELECT c.id, c.document_id, c.version_id, d.title, c.heading, c.content,
           c.start_char, c.end_char,
           ts_rank_cd(c.content_tsv, q.query, 32) AS score
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


def _snippet(content: str) -> str:
    content = " ".join(content.split())
    if len(content) <= SNIPPET_CHARS:
        return content
    cut = content.rfind(" ", 0, SNIPPET_CHARS)
    return content[: cut if cut > 0 else SNIPPET_CHARS] + "..."


def search_text(
    db: Session,
    *,
    organization_id: uuid.UUID,
    query: str,
    limit: int = 20,
) -> list[SearchHit]:
    query = " ".join(query.split())
    if not query:
        raise InvalidInputError("The search is empty")
    if len(query) > MAX_QUERY_CHARS:
        raise InvalidInputError(f"The search is longer than {MAX_QUERY_CHARS} characters")
    limit = max(1, min(limit, MAX_RESULTS))

    rows = db.execute(
        SEARCH_SQL,
        {"query": query, "organization_id": organization_id, "limit": limit},
    ).all()
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
