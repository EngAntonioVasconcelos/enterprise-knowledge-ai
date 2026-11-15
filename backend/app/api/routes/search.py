import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_roles
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.schemas.search import SearchHitResponse, SearchResponse
from app.services.search_service import MAX_QUERY_CHARS, MAX_RESULTS, search


router = APIRouter(
    prefix="/organizations/{organization_id}/search",
    tags=["Search"],
)

MEMBERS = require_roles(["owner", "admin", "member", "viewer"])


@router.get("/", response_model=SearchResponse)
def search_passages(
    organization_id: uuid.UUID,
    q: str = Query(min_length=1, max_length=MAX_QUERY_CHARS),
    limit: int = Query(default=20, ge=1, le=MAX_RESULTS),
    mode: Literal["hybrid", "keyword", "semantic"] = "hybrid",
    rerank: bool = Query(
        default=False,
        description="Reorder the first results with the reranker: better order, slower.",
    ),
    member: OrganizationMembership = Depends(MEMBERS),
    db: Session = Depends(get_db),
):
    """Passages by words and meaning, only from documents the caller may open."""
    result = search(
        db, organization_id=organization_id, query=q, limit=limit, mode=mode, rerank=rerank
    )
    return SearchResponse(
        query=q,
        mode=result.mode,
        note=result.note,
        reranked=result.reranked,
        results=[SearchHitResponse.model_validate(hit) for hit in result.hits],
    )
