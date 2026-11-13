from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session


CONTEXT_KEYS = {
    "auth_issuer": "app.auth_issuer",
    "auth_subject": "app.auth_subject",
    "user_id": "app.user_id",
    "organization_id": "app.organization_id",
}


def _get_context_values(session: Session) -> dict[str, str]:
    return {
        key: str(session.info.get(key) or "")
        for key in CONTEXT_KEYS
    }


def _apply_context(
    connection: Connection,
    session: Session,
) -> None:
    if connection.dialect.name != "postgresql":
        return

    values = _get_context_values(session)

    connection.execute(
        text(
            """
            SELECT
                set_config('app.auth_issuer', :auth_issuer, true),
                set_config('app.auth_subject', :auth_subject, true),
                set_config('app.user_id', :user_id, true),
                set_config('app.organization_id', :organization_id, true)
            """
        ),
        values,
    )


@event.listens_for(Session, "after_begin")
def apply_context_after_begin(
    session: Session,
    transaction,
    connection: Connection,
) -> None:
    _apply_context(connection, session)


def _apply_context_to_current_transaction(session: Session) -> None:
    if session.in_transaction():
        connection = session.connection()
        _apply_context(connection, session)
    else:
        session.connection()


def set_identity_context(
    session: Session,
    *,
    issuer: str,
    subject: str,
    user_id: UUID,
) -> None:
    if not issuer.strip() or not subject.strip():
        raise ValueError("Issuer and subject must not be empty")

    session.info.update(
        {
            "auth_issuer": issuer,
            "auth_subject": subject,
            "user_id": str(user_id),
            "organization_id": None,
        }
    )

    _apply_context_to_current_transaction(session)


def set_organization_context(
    session: Session,
    *,
    organization_id: UUID,
) -> None:
    if not session.info.get("user_id"):
        raise RuntimeError(
            "Authenticated user context must be established first"
        )

    existing_organization_id = session.info.get("organization_id")

    if (
        existing_organization_id is not None
        and existing_organization_id != str(organization_id)
    ):
        raise RuntimeError(
            "Organization context cannot be changed within the same session"
        )

    session.info["organization_id"] = str(organization_id)

    _apply_context_to_current_transaction(session)
