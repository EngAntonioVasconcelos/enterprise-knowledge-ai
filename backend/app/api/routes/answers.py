import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_roles
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.schemas.answer import AnswerRequest, AnswerResponse, AnswerSourceResponse
from app.services.answer_service import answer_question
from app.services.history_service import record_answer


router = APIRouter(
    prefix="/organizations/{organization_id}/answers",
    tags=["Answers"],
)

MEMBERS = require_roles(["owner", "admin", "member", "viewer"])

logger = logging.getLogger("eka.history")


@router.post("/", response_model=AnswerResponse)
def answer(
    organization_id: uuid.UUID,
    body: AnswerRequest,
    member: OrganizationMembership = Depends(MEMBERS),
    db: Session = Depends(get_db),
):
    """An answer with citations from the documents the caller may open, or
    an honest "I could not find a reliable answer" with the sources."""
    result = answer_question(
        db,
        organization_id=organization_id,
        question=body.question,
        interface_language=body.interface_language,
    )
    cited = set(result.cited)
    response = AnswerResponse(
        question=body.question,
        answer=result.answer,
        abstained=result.abstained,
        verified=result.verified,
        language=result.language,
        sources=[
            AnswerSourceResponse(
                number=source.number,
                cited=source.number in cited,
                chunk_id=source.hit.chunk_id,
                document_id=source.hit.document_id,
                version_id=source.hit.version_id,
                title=source.hit.title,
                heading=source.hit.heading,
                snippet=source.hit.snippet,
                start_char=source.hit.start_char,
                end_char=source.hit.end_char,
            )
            for source in result.sources
        ],
        prompt_id=result.prompt_id,
        model=result.model,
        note=result.note,
        timings_ms=result.timings_ms,
    )
    _keep_in_history(db, member, response)
    return response


def _keep_in_history(
    db: Session, member: OrganizationMembership, response: AnswerResponse
) -> None:
    """Keeps the exchange in the person's history. A failure here never
    costs the person their answer."""
    try:
        kept = record_answer(
            db,
            organization=member.organization,
            user_id=member.user_id,
            question=response.question,
            answer=response.answer,
            abstained=response.abstained,
            verified=response.verified,
            language=response.language,
            sources=[source.model_dump(mode="json") for source in response.sources],
        )
        if kept is not None:
            db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        logger.warning("history not kept: %s", type(error).__name__)
