import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_roles
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.schemas.search import SearchHitResponse, SearchResponse
from app.services.search_service import MAX_QUERY_CHARS, MAX_RESULTS, search_text


router = APIRouter(
    prefix="/organizations/{organization_id}/search",
    tags=["Search"],
)

MEMBERS = require_roles(["owner", "admin", "member", "viewer"])


@router.get("/", response_model=SearchResponse)
def search(
    organization_id: uuid.UUID,
    q: str = Query(min_length=1, max_length=MAX_QUERY_CHARS),
    limit: int = Query(default=20, ge=1, le=MAX_RESULTS),
    member: OrganizationMembership = Depends(MEMBERS),
    db: Session = Depends(get_db),
):
    """Passages that match the words, only from documents the caller may open."""
    hits = search_text(db, organization_id=organization_id, query=q, limit=limit)
    return SearchResponse(
        query=q,
        results=[SearchHitResponse.model_validate(hit) for hit in hits],
    )
