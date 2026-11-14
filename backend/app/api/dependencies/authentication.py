from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClientError
from jwt.exceptions import PyJWKClientConnectionError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_access_token
from app.db.context import (
    set_authentication_context,
    set_identity_context,
)
from app.db.session import get_db
from app.models.user import User
from app.services.authentication_service import (
    AccountUnavailableError,
    provision_authenticated_user,
    resolve_authenticated_user,
)


bearer_scheme = HTTPBearer(auto_error=False)

FULL_NAME_MAX_LENGTH = 150


def _profile_claim(payload: dict, name: str):
    namespace = settings.OIDC_CLAIMS_NAMESPACE or ""

    if namespace and f"{namespace}{name}" in payload:
        return payload[f"{namespace}{name}"]

    return payload.get(name)


def _provision_on_first_login(
    db: Session,
    payload: dict,
    unauthorized_exception: HTTPException,
) -> User:
    email = _profile_claim(payload, "email")
    email_verified = _profile_claim(payload, "email_verified")
    name = _profile_claim(payload, "name")

    if not isinstance(email, str) or "@" not in email:
        raise unauthorized_exception

    # Only an e-mail the identity provider verified may create an account
    # or link to an existing one; anything else would allow account takeover.
    if email_verified is not True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A verified email address is required.",
        )

    if isinstance(name, str) and name.strip():
        full_name = name.strip()
    else:
        full_name = email.split("@", 1)[0]

    try:
        user = provision_authenticated_user(
            db,
            email=email,
            full_name=full_name[:FULL_NAME_MAX_LENGTH],
        )
        # The account must exist whatever happens to the rest of the request.
        db.commit()

    except AccountUnavailableError:
        db.rollback()
        raise unauthorized_exception from None

    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required or invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized_exception

    try:
        payload = verify_access_token(credentials.credentials)

    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not properly configured",
        ) from None

    except PyJWKClientConnectionError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable",
        ) from None

    except (InvalidTokenError, PyJWKClientError):
        raise unauthorized_exception from None

    issuer = payload.get("iss")
    subject = payload.get("sub")

    if (
        not isinstance(issuer, str)
        or not issuer.strip()
        or not isinstance(subject, str)
        or not subject.strip()
    ):
        raise unauthorized_exception

    set_authentication_context(
        db,
        issuer=issuer,
        subject=subject,
    )

    user = resolve_authenticated_user(
        db,
        issuer=issuer,
        subject=subject,
    )

    if user is None:
        user = _provision_on_first_login(
            db,
            payload,
            unauthorized_exception,
        )

    set_identity_context(
        db,
        issuer=issuer,
        subject=subject,
        user_id=user.id,
    )

    return user
