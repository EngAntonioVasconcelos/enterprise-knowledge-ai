import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_roles
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.schemas.answer import AnswerRequest, AnswerResponse, AnswerSourceResponse
from app.services.answer_service import AgentLimits, ToolRecorder, answer_question, gap_reason
from app.services.dashboard_service import record_event
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
        previous_questions=body.previous_questions,
        limits=AgentLimits(
            max_steps=member.organization.agent_max_steps,
            max_tool_calls=member.organization.agent_max_tool_calls,
        ),
        on_tool_call=_tool_recorder(db, member.organization_id),
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
    _count_for_dashboard(db, member, response, gap_reason(result))
    return response


def _tool_recorder(db: Session, organization_id: uuid.UUID) -> ToolRecorder | None:
    """Writes each tool call of the agent to the audit log: the tool, the
    step, how many results and how long. Never the question, never the
    person. A failure here never costs the person their answer."""
    if db.get_bind().dialect.name != "postgresql":
        return None

    def record(tool: str, step: int, results: int, ms: float) -> None:
        try:
            with db.begin_nested():
                db.execute(
                    text(
                        "SELECT app_private.record_agent_tool_call("
                        ":organization_id, :tool, :step, :results, :ms)"
                    ),
                    {
                        "organization_id": organization_id,
                        "tool": tool,
                        "step": step,
                        "results": results,
                        "ms": round(ms),
                    },
                )
        except SQLAlchemyError as error:
            logger.warning("tool call not audited: %s", type(error).__name__)

    return record


def _count_for_dashboard(
    db: Session,
    member: OrganizationMembership,
    response: AnswerResponse,
    reason: str | None,
) -> None:
    """Counts the answer for the dashboard: no person, no text. A failure
    here never costs the person their answer."""
    try:
        record_event(
            db,
            organization_id=member.organization_id,
            abstained=response.abstained,
            verified=response.verified,
            language=response.language,
            cited_document_ids=[
                source.document_id for source in response.sources if source.cited
            ],
            # Only for "no reliable answer": where people looked (AL-3).
            consulted_document_ids=(
                [source.document_id for source in response.sources] if reason else []
            ),
            gap_reason=reason,
        )
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        logger.warning("answer not counted: %s", type(error).__name__)


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
