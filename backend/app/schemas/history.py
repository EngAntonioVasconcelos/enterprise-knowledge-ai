import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.answer import AnswerSourceResponse


class HistoryItem(BaseModel):
    id: uuid.UUID
    question: str
    abstained: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HistoryEntry(BaseModel):
    id: uuid.UUID
    question: str
    # None when a cited document can no longer be read: ask again.
    answer: str | None
    abstained: bool
    verified: bool
    language: str
    created_at: datetime
    sources: list[AnswerSourceResponse]
    hidden: bool
    # A cited document changed since this answer.
    outdated: bool
