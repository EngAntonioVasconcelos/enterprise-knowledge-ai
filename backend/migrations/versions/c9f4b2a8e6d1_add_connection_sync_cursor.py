"""Remember where each connection's last sync stopped.

Revision ID: c9f4b2a8e6d1
Revises: a2d7c4e9f1b6

The cursor is the connector's own position in the source's change feed
(a change token, a timestamp). It is not a secret. Only the worker moves
it; the API cannot, so a request can never make a sync skip changes.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9f4b2a8e6d1"
down_revision: Union[str, Sequence[str], None] = "a2d7c4e9f1b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "data_connections",
        sa.Column("sync_cursor", sa.Text(), nullable=True),
    )
    op.execute("""
        GRANT UPDATE (sync_cursor) ON public.data_connections TO eka_worker;
    """)


def downgrade() -> None:
    op.execute("""
        REVOKE UPDATE (sync_cursor) ON public.data_connections
            FROM eka_worker;
    """)
    op.drop_column("data_connections", "sync_cursor")
