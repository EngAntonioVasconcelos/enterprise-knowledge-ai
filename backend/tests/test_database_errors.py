import pytest
from sqlalchemy.exc import DBAPIError

from app.core.database_errors import database_rule_violation


def _error(message):
    return DBAPIError("SELECT 1", {}, Exception(message))


@pytest.mark.parametrize(
    ("message", "status_code"),
    [
        ("ERROR: organization limit reached", 403),
        ("ERROR: organization is not active", 409),
        ("ERROR: organization status can only be changed by the platform", 403),
    ],
)
def test_known_database_rules_map_to_http_errors(message, status_code):
    assert database_rule_violation(_error(message))[0] == status_code


def test_unknown_database_errors_are_not_mapped():
    assert database_rule_violation(_error("deadlock detected")) is None
