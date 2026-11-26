import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentSource(BaseModel):
    provider: str
    name: str


class DocumentResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    connection_id: uuid.UUID
    title: str
    mime_type: str | None = None
    status: str
    current_version_id: uuid.UUID | None = None
    last_synced_at: datetime | None = None
    updated_at: datetime
    # Where it comes from and the kind of sharing, never who (AL-9):
    # organization, only_you, people or source.
    source: DocumentSource | None = None
    audience: str | None = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class DocumentStatistics(BaseModel):
    total: int
    by_status: dict[str, int]

    model_config = ConfigDict(extra="forbid")


class DocumentExcerpt(BaseModel):
    heading: str | None = None
    content: str


class DocumentPage(BaseModel):
    """One document for its own page (AL-10): what it is, where it comes
    from, the kind of sharing, when it was last read, the first passages
    the assistant answers from, and why the last reading failed, if it did."""

    document: DocumentResponse
    read_at: datetime | None = None
    passages: int = 0
    excerpt: list[DocumentExcerpt] = []
    failure: str | None = None
