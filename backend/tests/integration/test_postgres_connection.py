import pytest
from sqlalchemy import inspect


pytestmark = pytest.mark.integration


def test_postgres_test_database_connection(postgres_engine):
    inspector = inspect(postgres_engine)

    tables = set(inspector.get_table_names())

    expected_tables = {
        "users",
        "organizations",
        "organization_memberships",
        "authentication_identities",
        "documents",
        "alembic_version",
    }

    assert expected_tables.issubset(tables)
