from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClientError
from jwt.exceptions import PyJWKClientConnectionError
from sqlalchemy.orm import Session

from app.core.security import verify_access_token
from app.db.context import set_identity_context
from app.db.session import get_db
from app.models.user import User
from app.services.authentication_service import resolve_authenticated_user


bearer_scheme = HTTPBearer(auto_error=False)


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

    user = resolve_authenticated_user(
        db,
        issuer=issuer,
        subject=subject,
    )

    if user is None:
        raise unauthorized_exception

    set_identity_context(
        db,
        issuer=issuer,
        subject=subject,
        user_id=user.id,
    )

    return user
