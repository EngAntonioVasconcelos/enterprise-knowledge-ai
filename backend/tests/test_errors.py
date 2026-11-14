import asyncio
import json

import pytest

from app.core.errors import (
    ConflictError,
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
    domain_error_handler,
)
from app.services.membership_service import MembershipPermissionError


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (InvalidInputError("Organization name cannot be empty"), 400),
        (NotFoundError("Organization not found"), 404),
        (ConflictError("Membership already exists"), 409),
        (ForbiddenError("Insufficient organization permissions"), 403),
        (MembershipPermissionError("Only an owner can do this"), 403),
    ],
)
def test_domain_errors_map_to_their_status_and_message(error, status_code):
    response = asyncio.run(domain_error_handler(None, error))

    assert response.status_code == status_code
    assert json.loads(response.body)["detail"] == error.message + "."


def test_former_value_errors_are_still_value_errors():
    # Callers that caught ValueError keep working during the migration.
    for error_type in (InvalidInputError, NotFoundError, ConflictError):
        assert issubclass(error_type, ValueError)

    assert issubclass(ForbiddenError, PermissionError)
