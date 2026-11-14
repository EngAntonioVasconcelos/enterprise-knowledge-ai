
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models.authentication_identity import AuthenticationIdentity
from app.models.user import User


class AccountUnavailableError(Exception):
    """The verified identity belongs to a disabled account or identity."""


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


def provision_authenticated_user(
    db: Session,
    *,
    email: str,
    full_name: str,
) -> User:
    """Create or link the account of the identity in the transaction context.

    The database function reads the issuer and subject that
    set_authentication_context placed in the transaction. It links an
    existing account only by this e-mail, which the caller must have
    confirmed as verified by the identity provider.
    """
    try:
        user_id = db.scalar(
            text("SELECT app_private.provision_user(:email, :full_name)"),
            {"email": email, "full_name": full_name},
        )
    except DBAPIError as exc:
        if "disabled" in str(exc.orig):
            raise AccountUnavailableError from exc
        raise

    return db.get(User, user_id)
