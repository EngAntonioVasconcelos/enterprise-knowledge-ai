"""The organization dashboard (AK-7): counts, never people or questions.

Answers are counted from answer_events, which hold no person and no text
(migration f2c7a9e4b6d1). The most cited documents are shown only when the
viewer can open them: a private document never appears by its title.
"""

import uuid
from collections import Counter
from datetime import date, timedelta

from sqlalchemy import func, insert, select, text
from sqlalchemy.orm import Session

from app.models.answer_event import AnswerEvent
from app.models.document import Document
from app.models.membership import OrganizationMembership
from app.services.document_permission_service import document_statistics


DAYS = 30
TOP_DOCUMENTS = 10
LANGUAGES = ("pt", "en", "fr")


def record_event(
    db: Session,
    *,
    organization_id: uuid.UUID,
    abstained: bool,
    verified: bool,
    language: str,
    cited_document_ids: list[uuid.UUID],
) -> None:
    unique = list(dict.fromkeys(str(document_id) for document_id in cited_document_ids))
    # A plain INSERT: members write counts they are not allowed to read
    # back, so nothing may be returned (the day is set by the database).
    db.execute(
        insert(AnswerEvent).values(
            id=uuid.uuid4(),
            organization_id=organization_id,
            abstained=abstained,
            verified=verified,
            language=language if language in LANGUAGES else "pt",
            cited_document_ids=unique[:10],
        )
    )


def _today(db: Session) -> date:
    # The database's date, the same one the rows were written with.
    return db.scalar(select(func.current_date()))


def build_dashboard(db: Session, *, organization_id: uuid.UUID) -> dict:
    today = _today(db)
    if isinstance(today, str):  # SQLite returns text
        today = date.fromisoformat(today)
    first = today - timedelta(days=DAYS - 1)

    rows = db.execute(
        select(
            AnswerEvent.answered_on,
            AnswerEvent.abstained,
            AnswerEvent.language,
            AnswerEvent.cited_document_ids,
        ).where(
            AnswerEvent.organization_id == organization_id,
            AnswerEvent.answered_on >= first,
        )
    ).all()

    per_day: dict[date, list[int]] = {
        first + timedelta(days=offset): [0, 0] for offset in range(DAYS)
    }
    languages: Counter[str] = Counter()
    citations: Counter[str] = Counter()
    for answered_on, abstained, language, cited in rows:
        if isinstance(answered_on, str):
            answered_on = date.fromisoformat(answered_on)
        day = per_day.get(answered_on)
        if day is None:
            continue
        day[0] += 1
        day[1] += int(abstained)
        languages[language] += 1
        citations.update(str(document_id) for document_id in cited or [])

    questions = sum(day[0] for day in per_day.values())
    unanswered = sum(day[1] for day in per_day.values())

    return {
        "days": [
            {"date": day, "questions": counts[0], "unanswered": counts[1]}
            for day, counts in per_day.items()
        ],
        "questions": questions,
        "unanswered": unanswered,
        "languages": {language: languages.get(language, 0) for language in LANGUAGES},
        "top_documents": _readable_top(db, organization_id, citations),
        "documents": document_statistics(db, organization_id=organization_id)["by_status"],
        "members": db.scalar(
            select(func.count())
            .select_from(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.is_active.is_(True),
            )
        )
        or 0,
    }


def _readable_top(
    db: Session, organization_id: uuid.UUID, citations: Counter[str]
) -> list[dict]:
    if not citations:
        return []
    ids = [uuid.UUID(document_id) for document_id in citations]
    # Read as the viewer: documents they cannot open are not returned.
    titles = {
        str(document_id): title
        for document_id, title in db.execute(
            select(Document.id, Document.title).where(
                Document.id.in_(ids),
                Document.organization_id == organization_id,
                Document.status == "active",
            )
        )
    }
    ranked = sorted(
        (
            (count, titles[document_id], document_id)
            for document_id, count in citations.items()
            if document_id in titles
        ),
        key=lambda item: (-item[0], item[1].lower()),
    )
    return [
        {"document_id": document_id, "title": title, "citations": count}
        for count, title, document_id in ranked[:TOP_DOCUMENTS]
    ]


def purge_old_events(db: Session) -> int:
    """Deletes events older than a year (worker, PostgreSQL)."""
    return int(db.execute(text("SELECT app_private.purge_old_answer_events()")).scalar_one())
