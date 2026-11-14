"""Turn refusals raised by database rules into clear API responses.

Business rules that must hold whatever the caller (row-level security,
triggers) raise errors with fixed messages. Each known message maps to one
HTTP status and one message for the user; anything else stays a 500.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError


DATABASE_RULES = (
    (
        "organization limit reached",
        status.HTTP_403_FORBIDDEN,
        "You have reached the maximum number of organizations you can create.",
    ),
    (
        "organization is not active",
        status.HTTP_409_CONFLICT,
        "This organization is not active and cannot be changed.",
    ),
    (
        "organization status can only be changed by the platform",
        status.HTTP_403_FORBIDDEN,
        "The organization status cannot be changed here.",
    ),
)


def database_rule_violation(exc: DBAPIError) -> tuple[int, str] | None:
    message = str(exc.orig)

    for fragment, status_code, detail in DATABASE_RULES:
        if fragment in message:
            return status_code, detail

    return None


async def database_error_handler(
    request: Request,
    exc: DBAPIError,
) -> JSONResponse:
    violation = database_rule_violation(exc)

    if violation is None:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected database error occurred."},
        )

    status_code, detail = violation

    return JSONResponse(status_code=status_code, content={"detail": detail})
