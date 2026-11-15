"""Database connections keep a catalog of their tables and columns.

Revision ID: f9d2b6e4a1c7
Revises: e7c3a9f5b2d8

The catalog tells the agent what it may query in a customer's database
(names, types, comments, row estimates). It never holds data. Only the
worker writes it, because only the worker can open the credentials.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f9d2b6e4a1c7"
down_revision: Union[str, Sequence[str], None] = "e7c3a9f5b2d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "data_connections",
        sa.Column("catalog", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "data_connections",
        sa.Column("catalog_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_data_connections_catalog",
        "data_connections",
        "catalog IS NULL OR jsonb_typeof(catalog) = 'object'",
    )
    op.execute("""
        GRANT UPDATE (catalog, catalog_updated_at)
            ON public.data_connections TO eka_worker;
    """)


def downgrade() -> None:
    op.execute("""
        REVOKE UPDATE (catalog, catalog_updated_at)
            ON public.data_connections FROM eka_worker;
    """)
    op.drop_constraint("ck_data_connections_catalog", "data_connections")
    op.drop_column("data_connections", "catalog_updated_at")
    op.drop_column("data_connections", "catalog")
