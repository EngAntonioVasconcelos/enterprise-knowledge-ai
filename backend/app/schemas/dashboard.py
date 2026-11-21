import uuid
from datetime import date

from pydantic import BaseModel


class DashboardDay(BaseModel):
    date: date
    questions: int
    unanswered: int


class DashboardDocument(BaseModel):
    document_id: uuid.UUID
    title: str
    citations: int


class Dashboard(BaseModel):
    """Counts for the last 30 days. Never who asked, never what."""

    days: list[DashboardDay]
    questions: int
    # Answered with "no safe answer": where the documents fall short.
    unanswered: int
    languages: dict[str, int]
    # Only documents the viewer can open.
    top_documents: list[DashboardDocument]
    documents: dict[str, int]
    members: int


class GapDocument(BaseModel):
    document_id: uuid.UUID
    title: str
    # Questions without a safe answer that read this document.
    questions: int


class Gaps(BaseModel):
    """Where the documents fall short (AL-3). Never who asked, never what."""

    days: int
    unanswered: int
    # no_sources, not_found, checks, not_relevant
    reasons: dict[str, int]
    documents: list[GapDocument]
    hidden_documents: int
    min_questions: int
