"""Each person's question history (AK-6).

Only the person who asked reads an entry: the database enforces it (RLS,
migration e6b1d4a8c2f9) and every query here filters by that person too.
An entry is shown again only while its sources are still readable: if a
cited document was removed or the person lost access to it, the answer is
hidden and the person can ask again.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.organization import Organization
from app.models.question_history import QuestionHistory


LANGUAGES = ("pt", "en", "fr")
MAX_ANSWER_CHARS = 20000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _kept_since(retention_days: int) -> datetime | None:
    """The oldest moment still kept, or None when nothing is kept."""
    if retention_days <= 0:
        return None
    return _now() - timedelta(days=retention_days)


def record_answer(
    db: Session,
    *,
    organization: Organization,
    user_id: uuid.UUID,
    question: str,
    answer: str,
    abstained: bool,
    verified: bool,
    language: str,
    sources: list[dict],
) -> QuestionHistory | None:
    """Keeps the exchange, unless the organization keeps no history."""
    if organization.history_retention_days <= 0:
        return None
    entry = QuestionHistory(
        organization_id=organization.id,
        user_id=user_id,
        question=question.strip()[:500],
        answer=answer[:MAX_ANSWER_CHARS],
        abstained=abstained,
        verified=verified,
        language=language if language in LANGUAGES else "pt",
        sources=sources,
    )
    db.add(entry)
    db.flush()
    return entry


def list_entries(
    db: Session,
    *,
    organization: Organization,
    user_id: uuid.UUID,
    limit: int = 50,
) -> list[QuestionHistory]:
    since = _kept_since(organization.history_retention_days)
    if since is None:
        return []
    return list(
        db.scalars(
            select(QuestionHistory)
            .where(
                QuestionHistory.organization_id == organization.id,
                QuestionHistory.user_id == user_id,
                QuestionHistory.created_at >= since,
            )
            .order_by(QuestionHistory.created_at.desc(), QuestionHistory.id)
            .limit(limit)
        )
    )


@dataclass
class OpenedEntry:
    entry: QuestionHistory
    # None when a cited document can no longer be read.
    answer: str | None
    sources: list[dict]
    hidden: bool
    # A cited document has a newer version than the one quoted.
    outdated: bool


def open_entry(
    db: Session,
    *,
    organization: Organization,
    user_id: uuid.UUID,
    entry_id: uuid.UUID,
) -> OpenedEntry | None:
    since = _kept_since(organization.history_retention_days)
    if since is None:
        return None
    entry = db.scalar(
        select(QuestionHistory).where(
            QuestionHistory.id == entry_id,
            QuestionHistory.organization_id == organization.id,
            QuestionHistory.user_id == user_id,
        )
    )
    if entry is None or _aware(entry.created_at) < since:
        return None

    document_ids = {
        uuid.UUID(str(source["document_id"])) for source in entry.sources
    }
    # Read as the person: documents they cannot open are not returned.
    readable = {
        str(document_id): str(version_id)
        for document_id, version_id in db.execute(
            select(Document.id, Document.current_version_id).where(
                Document.id.in_(document_ids),
                Document.organization_id == organization.id,
                Document.status == "active",
            )
        )
    } if document_ids else {}

    cited = [source for source in entry.sources if source.get("cited")]
    hidden = any(str(source["document_id"]) not in readable for source in cited)
    outdated = any(
        readable.get(str(source["document_id"])) not in (None, str(source["version_id"]))
        for source in cited
    )
    return OpenedEntry(
        entry=entry,
        answer=None if hidden else entry.answer,
        sources=[
            source
            for source in entry.sources
            if str(source["document_id"]) in readable
        ],
        hidden=hidden,
        outdated=outdated and not hidden,
    )


def delete_entry(
    db: Session,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    entry_id: uuid.UUID,
) -> bool:
    result = db.execute(
        delete(QuestionHistory).where(
            QuestionHistory.id == entry_id,
            QuestionHistory.organization_id == organization_id,
            QuestionHistory.user_id == user_id,
        )
    )
    return bool(result.rowcount)


def delete_all(
    db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> int:
    result = db.execute(
        delete(QuestionHistory).where(
            QuestionHistory.organization_id == organization_id,
            QuestionHistory.user_id == user_id,
        )
    )
    return result.rowcount or 0


def purge_expired(db: Session) -> int:
    """Deletes what each organization no longer keeps (worker, PostgreSQL)."""
    return int(
        db.execute(text("SELECT app_private.purge_expired_questions()")).scalar_one()
    )
