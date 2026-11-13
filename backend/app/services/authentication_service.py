
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.authentication_identity import AuthenticationIdentity
from app.models.user import User


def resolve_authenticated_user(
    db: Session,
    *,
    issuer: str,
    subject: str,
) -> User | None:
    statement = (
        select(AuthenticationIdentity)
        .where(
            AuthenticationIdentity.issuer == issuer,
            AuthenticationIdentity.subject == subject,
            AuthenticationIdentity.is_active.is_(True),
        )
    )

    identity = db.scalar(statement)

    if identity is None:
        return None

    user = identity.user

    if not user.is_active:
        return None

    return user
