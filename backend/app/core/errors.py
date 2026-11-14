"""Business rules refused by the services, as typed exceptions.

Each type carries the HTTP status it means, so routes do not compare error
messages to decide the response. Every type that replaced a ValueError still
subclasses it, so existing callers keep working while they move over.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse


class DomainError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidInputError(DomainError, ValueError):
    status_code = status.HTTP_400_BAD_REQUEST


class NotFoundError(DomainError, ValueError):
    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(DomainError, ValueError):
    status_code = status.HTTP_409_CONFLICT


class ForbiddenError(DomainError, PermissionError):
    status_code = status.HTTP_403_FORBIDDEN


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    detail = exc.message if exc.message.endswith(".") else exc.message + "."

    return JSONResponse(status_code=exc.status_code, content={"detail": detail})
