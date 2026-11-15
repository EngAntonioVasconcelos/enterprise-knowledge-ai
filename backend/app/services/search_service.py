"""Search the passages a person may read (Phase 6, RAG Core).

Two searches, then one list:
- by words (PostgreSQL full text): exact terms, names, codes; accents and
  case are ignored;
- by meaning (vectors, pgvector): synonyms, paraphrases, another language;
- hybrid (default): both lists merged with Reciprocal Rank Fusion. Each
  passage scores 1 / (60 + its position) in every list it appears in; a
  passage near the top of both lists wins. Positions, not raw scores, are
  combined, because word scores and vector distances are not comparable.
  Weighted fusion (default): a passage found by words votes in proportion
  to how much of the question it matches (its coverage), and only if it
  matches at least half of the meaningful words or one of the question's
  codes. Sharing one common word ("days") with a question in another
  language is not evidence: with equal votes such passages pushed down the
  right answer found by meaning (AI-1: hybrid MRR 0.79 against 0.87 for
  meaning alone, 0.27 against 0.88 for English questions on Portuguese
  documents). Paraphrases are left to search by meaning.

Optionally (rerank=True) a cross-encoder reads the question next to each of
the first candidates and puts them in a new order (app/services/reranking).
It only reorders passages the person may already read.

Permissions are not checked here: the queries run as the person, and the
database returns only passages of documents they may open (row-level
security on documents, document_chunks and chunk_embeddings). Only the
current version of active documents is searched.

If vectors are unavailable (model not downloaded, disabled), hybrid search
falls back to words and says so in the result.
"""

import logging
import re
import unicodedata
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
from app.core.config import settings
from app.services.reranking import RerankUnavailableError, get_reranker


logger = logging.getLogger("eka.search")

MAX_QUERY_CHARS = 500
MAX_RESULTS = 50
SNIPPET_CHARS = 320
CANDIDATES = 40
RRF_K = 60
MODES = ("hybrid", "keyword", "semantic")
FUSIONS = ("weighted", "rrf")
# In the weighted fusion, a passage found by words votes only if it matches
# at least this share of the question's meaningful words. One with a code
# or number of the question ("WS-09", "4400") always does: codes are
# precise evidence.
MIN_COVERAGE = 0.5

# Words that carry no meaning on their own, in Portuguese and English. A
# question in natural language ("quantos dias de ferias tenho por ano?")
# is searched as "any of the remaining words", ranked by how many match and
# how close together they are; requiring every word would find nothing.
STOPWORDS = frozenset("""
a o as os um uma uns umas de do da dos das em no na nos nas por para pelo pela
com sem e ou que se ao aos nao como qual quais quanto quantos quanta quantas quando
onde quem porque eu tu ele ela nos vos eles elas me te lhe meu minha meus minhas
seu sua seus suas tenho tem temos posso pode podem ser sao esta estao isso este
essa esse mais muito muita ja ate the an of to in on at for by with from and or
is are was were be been do does did can could should would will how what when
where who whom which why my your our their i you we they it its this that these
those me us there here if about into than then so not no yes get got have has
""".split())
TOKEN = re.compile(r"[0-9a-z]+(?:[-./][0-9a-z]+)*")
ADVANCED = re.compile(r'"|(^|\s)-\S|\sor\s', re.IGNORECASE)


def _plain(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def keyword_terms(query: str) -> list[str]:
    """The meaningful words of a plain question (none for advanced syntax)."""
    if ADVANCED.search(query):
        return []
    tokens = TOKEN.findall(_plain(query))
    return list(dict.fromkeys([t for t in tokens if t not in STOPWORDS] or tokens))


def keyword_query(query: str) -> str:
    """The text given to websearch_to_tsquery.

    Advanced syntax ("exact phrase", -exclude, or) is kept as typed;
    otherwise the meaningful words are joined with "or".
    """
    return " or ".join(keyword_terms(query)) or query


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
    # Share of the question's meaningful words this passage contains (search
    # by words only; None when not measured).
    coverage: float | None = None
    rerank_score: float | None = None
    # The full passage, for the reranker and the answer step; not returned
    # by the API (the snippet is).
    content: str = ""


@dataclass(frozen=True)
class SearchResult:
    mode: str
    hits: list[SearchHit]
    note: str | None = None
    reranked: bool = False


COLUMNS = """
    c.id, c.document_id, c.version_id, d.title, c.heading, c.content,
    c.start_char, c.end_char
"""

# matched: how many of the meaningful words the passage contains; codes:
# how many of the question's codes and numbers. Passages with the codes
# come first, then those that match more of the question, then the
# PostgreSQL rank.
KEYWORD_SQL = text(f"""
    SELECT {COLUMNS}, ts_rank_cd(c.content_tsv, q.query, 32) AS score,
           (SELECT count(*) FROM unnest(CAST(:terms AS text[])) AS t(term)
             WHERE c.content_tsv @@ plainto_tsquery('simple', t.term)) AS matched,
           (SELECT count(*) FROM unnest(CAST(:codes AS text[])) AS t(term)
             WHERE c.content_tsv @@ plainto_tsquery('simple', t.term)) AS codes
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
    ORDER BY codes DESC, matched DESC, score DESC, d.title, c.ordinal, c.id
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


def _hits(rows, terms: list[str] | None = None) -> list[SearchHit]:
    hits = []
    for row in rows:
        coverage = None
        if terms:
            coverage = row.matched / len(terms)
            if row.codes:
                coverage = max(coverage, MIN_COVERAGE)
        hits.append(
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
                coverage=coverage,
                content=row[5],
            )
        )
    return hits


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
    terms = keyword_terms(query)
    rows = db.execute(
        KEYWORD_SQL,
        {
            "query": keyword_query(query),
            "terms": terms,
            "codes": [t for t in terms if any(ch.isdigit() for ch in t)],
            "organization_id": organization_id,
            "limit": limit,
        },
    ).all()
    return [replace(hit, keyword_rank=i + 1) for i, hit in enumerate(_hits(rows, terms))]


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


def _vote(hit: SearchHit, fusion: str) -> float:
    """How much a passage found by words counts (1 = a full vote)."""
    if fusion == "rrf" or hit.coverage is None:
        return 1.0
    return hit.coverage if hit.coverage >= MIN_COVERAGE else 0.0


def fuse(
    keyword: list[SearchHit],
    semantic: list[SearchHit],
    limit: int,
    fusion: str = "weighted",
) -> list[SearchHit]:
    """Reciprocal Rank Fusion of two ranked lists.

    fusion="weighted" (default) weighs each word vote by its coverage and
    ignores passages below MIN_COVERAGE; "rrf" gives every passage a full
    vote (the first version, kept to compare).
    """
    merged: dict[uuid.UUID, SearchHit] = {}
    scores: dict[uuid.UUID, float] = {}
    for hits, field in ((keyword, "keyword_rank"), (semantic, "semantic_rank")):
        for rank, hit in enumerate(hits, start=1):
            weight = _vote(hit, fusion) if field == "keyword_rank" else 1.0
            if weight == 0.0:
                continue
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + weight / (RRF_K + rank)
            current = merged.get(hit.chunk_id, hit)
            extra = {"coverage": hit.coverage} if field == "keyword_rank" else {}
            merged[hit.chunk_id] = replace(current, **{field: rank}, **extra)
    # Ties are common (two passages each found by one method at the same
    # rank). Break them the same way every time, so a question always
    # returns the same order: best single rank, then title, then position.
    def order(chunk_id: uuid.UUID):
        hit = merged[chunk_id]
        ranks = [r for r in (hit.keyword_rank, hit.semantic_rank) if r is not None]
        return (-scores[chunk_id], min(ranks), hit.title, hit.start_char, str(chunk_id))

    ordered = sorted(merged, key=order)
    return [replace(merged[c], score=round(scores[c], 6)) for c in ordered[:limit]]


def search(
    db: Session,
    *,
    organization_id: uuid.UUID,
    query: str,
    limit: int = 20,
    mode: str = "hybrid",
    rerank: bool = False,
    fusion: str = "weighted",
    rerank_candidates: int | None = None,
    rerank_max_chars: int | None = None,
) -> SearchResult:
    if mode not in MODES:
        raise InvalidInputError(f"mode must be one of: {', '.join(MODES)}")
    if fusion not in FUSIONS:
        raise InvalidInputError(f"fusion must be one of: {', '.join(FUSIONS)}")
    query, limit = _clean(query, limit)
    if not rerank:
        return _search(db, organization_id, query, limit, mode, fusion)

    candidates = rerank_candidates or settings.RERANK_CANDIDATES
    max_chars = settings.RERANK_MAX_CHARS if rerank_max_chars is None else rerank_max_chars
    # The reranker reorders the first candidates; ask for at least that many.
    result = _search(db, organization_id, query, max(limit, candidates), mode, fusion)
    try:
        hits = rerank_hits(query, result.hits, candidates=candidates, max_chars=max_chars)
    except RerankUnavailableError as exc:
        logger.warning("reranking unavailable: %s", exc)
        note = "Reranking is unavailable; results are in search order."
        return replace(
            result,
            hits=result.hits[:limit],
            note=f"{result.note} {note}" if result.note else note,
        )
    return replace(result, hits=hits[:limit], reranked=True)


def rerank_text(hit: SearchHit, max_chars: int) -> str:
    """What the reranker reads: where the passage is, then its start."""
    content = " ".join((hit.content or hit.snippet).split())
    if max_chars and len(content) > max_chars:
        cut = content.rfind(" ", 0, max_chars)
        content = content[: cut if cut > 0 else max_chars]
    place = " - ".join(part for part in (hit.title, hit.heading) if part)
    return f"{place}\n{content}" if place else content


def rerank_hits(
    query: str, hits: list[SearchHit], *, candidates: int = 10, max_chars: int = 0
) -> list[SearchHit]:
    """The first candidates in the reranker's order; the rest keep theirs."""
    head, tail = hits[:candidates], hits[candidates:]
    if not head:
        return hits
    reranker = get_reranker()
    scores = reranker.score(query, [rerank_text(hit, max_chars) for hit in head])
    scored = [replace(hit, rerank_score=round(float(s), 6)) for hit, s in zip(head, scores)]
    # Stable: equal reranker scores keep the search order.
    ordered = sorted(range(len(scored)), key=lambda i: (-scored[i].rerank_score, i))
    return [scored[i] for i in ordered] + tail


def _search(
    db: Session,
    organization_id: uuid.UUID,
    query: str,
    limit: int,
    mode: str,
    fusion: str,
) -> SearchResult:
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
    return SearchResult("hybrid", fuse(keyword, semantic, limit, fusion))


def search_text(
    db: Session, *, organization_id: uuid.UUID, query: str, limit: int = 20
) -> list[SearchHit]:
    """Search by words only (the first version's entry point)."""
    query, limit = _clean(query, limit)
    return keyword_search(db, organization_id=organization_id, query=query, limit=limit)
