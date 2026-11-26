"""Source permissions and who may read what (Permission-aware AI).

The worker stores each document's permissions as the source reports them,
then the database resolves them into readers (document_access): active
members of the organization whose verified e-mail, or its domain, matches,
or everyone for organization-wide grants. Every read of documents and
versions is filtered by that table inside the query itself.

Fail closed: group grants give no access until group membership is
synchronized, and "anyone with the link" gives none unless an admin turns
on ``link_sharing_grants_organization`` for the connection.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.orm import Session

from app.core.errors import InvalidInputError
from app.models.document import Document
from app.models.document_access import (
    PERMISSION_ROLES,
    PRINCIPAL_TYPES,
    DocumentPermission,
)


class InvalidPermissionError(InvalidInputError):
    pass


@dataclass(frozen=True)
class SourcePermission:
    principal_type: str
    principal: str = ""
    role: str = "reader"

    def normalized(self) -> "SourcePermission":
        principal_type = self.principal_type.strip().lower()
        principal = self.principal.strip().lower()
        role = self.role.strip().lower()

        if principal_type not in PRINCIPAL_TYPES:
            raise InvalidPermissionError(
                f"Unknown principal type {principal_type}"
            )
        if role not in PERMISSION_ROLES:
            raise InvalidPermissionError(f"Unknown permission role {role}")

        if principal_type in ("anyone", "organization"):
            principal = ""
        elif principal_type in ("user", "group") and "@" not in principal:
            raise InvalidPermissionError(
                f"A {principal_type} permission needs an e-mail address"
            )
        elif principal_type == "domain" and (
            not principal or "@" in principal or "." not in principal
        ):
            raise InvalidPermissionError(
                "A domain permission needs a domain such as example.com"
            )

        return SourcePermission(principal_type, principal, role)


def _strongest(permissions: list[SourcePermission]) -> list[SourcePermission]:
    """One row per principal, keeping the strongest role."""
    rank = {role: index for index, role in enumerate(PERMISSION_ROLES)}
    best: dict[tuple[str, str], SourcePermission] = {}

    for permission in permissions:
        key = (permission.principal_type, permission.principal)
        current = best.get(key)
        if current is None or rank[permission.role] > rank[current.role]:
            best[key] = permission

    return list(best.values())


def replace_document_permissions(
    db: Session,
    *,
    document: Document,
    permissions: list[SourcePermission],
) -> int | None:
    """Store the source's permissions and resolve the readers.

    Returns the number of readers (None where the database cannot resolve,
    as in unit tests on SQLite).
    """
    normalized = _strongest([p.normalized() for p in permissions])

    db.execute(
        delete(DocumentPermission).where(
            DocumentPermission.document_id == document.id
        )
    )
    if normalized:
        db.execute(
            insert(DocumentPermission),
            [
                {
                    "id": uuid.uuid4(),
                    "document_id": document.id,
                    "organization_id": document.organization_id,
                    "principal_type": p.principal_type,
                    "principal": p.principal,
                    "role": p.role,
                }
                for p in normalized
            ],
        )

    if db.get_bind().dialect.name != "postgresql":
        return None

    return db.execute(
        text("SELECT app_private.resolve_document_access(:document_id)"),
        {"document_id": document.id},
    ).scalar_one()


def list_documents(
    db: Session,
    *,
    organization_id: uuid.UUID,
) -> list[Document]:
    """The documents the caller may read; row-level security filters."""
    return list(
        db.scalars(
            select(Document)
            .where(
                Document.organization_id == organization_id,
                Document.status != "removed",
            )
            .order_by(Document.title, Document.id)
        )
    )


def document_statistics(
    db: Session,
    *,
    organization_id: uuid.UUID,
) -> dict:
    """Counts by status for managers: numbers, never titles."""
    if db.get_bind().dialect.name == "postgresql":
        rows = db.execute(
            text(
                "SELECT status, documents "
                "FROM app_private.document_statistics(:organization_id)"
            ),
            {"organization_id": organization_id},
        ).all()
    else:
        rows = db.execute(
            select(Document.status, func.count())
            .where(Document.organization_id == organization_id)
            .group_by(Document.status)
        ).all()

    by_status = {status: int(count) for status, count in rows}
    return {"total": sum(by_status.values()), "by_status": by_status}


def document_audiences(db: Session, *, organization_id: uuid.UUID) -> dict[uuid.UUID, dict]:
    """For each document the caller can open: its source and the kind of
    sharing, from app_private.document_audiences. Never who."""
    if db.get_bind().dialect.name != "postgresql":
        return {}
    rows = db.execute(
        text("SELECT * FROM app_private.document_audiences(:organization_id)"),
        {"organization_id": organization_id},
    )
    return {
        row.document_id: {
            "source": {"provider": row.provider, "name": row.connection_name},
            "audience": row.audience,
        }
        for row in rows
    }


EXCERPT_PASSAGES = 3
EXCERPT_CHARACTERS = 700


def document_page(db: Session, *, organization_id: uuid.UUID, document_id: uuid.UUID) -> dict | None:
    """A readable document with its first passages, or None: not found and
    not allowed look the same. Row-level security decides what is read."""
    from app.models.document import Document, DocumentVersion
    from app.models.document_chunk import DocumentChunk

    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.organization_id == organization_id,
            Document.status != "removed",
        )
    )
    if document is None:
        return None
    audience = document_audiences(db, organization_id=organization_id).get(document.id, {})

    read_at = None
    passages = 0
    excerpt: list[dict] = []
    if document.current_version_id is not None:
        version = db.get(DocumentVersion, document.current_version_id)
        read_at = version.ready_at if version else None
        passages = db.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.version_id == document.current_version_id)
        ) or 0
        for chunk in db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.version_id == document.current_version_id)
            .order_by(DocumentChunk.ordinal)
            .limit(EXCERPT_PASSAGES)
        ):
            text_ = chunk.content.strip()
            if len(text_) > EXCERPT_CHARACTERS:
                text_ = text_[:EXCERPT_CHARACTERS].rsplit(" ", 1)[0] + "\u2026"
            excerpt.append({"heading": chunk.heading, "content": text_})

    newest = db.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.created_at.desc())
        .limit(1)
    )
    failure = newest.error if newest is not None and newest.status == "failed" else None

    return {
        "document": {**_as_response(document), **audience},
        "read_at": read_at,
        "passages": passages,
        "excerpt": excerpt,
        "failure": failure,
    }


def _as_response(document) -> dict:
    from app.schemas.document import DocumentResponse

    return DocumentResponse.model_validate(document).model_dump(exclude={"source", "audience"})
