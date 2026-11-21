"""Where questions found no safe answer, for the Gaps screen (AL-3).

Two columns on answer_events, filled only when there was no safe answer:
the documents given to the model (ids only, at most 10) and why there was
no answer. Still no person and no text. Older rows keep NULL and are not
counted. Access (RLS), grants and the one-year purge do not change.

Revision ID: c3f9a1e7d2b4
Revises: b8e4d2f6a1c3
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c3f9a1e7d2b4"
down_revision: Union[str, Sequence[str], None] = "b8e4d2f6a1c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "answer_events",
        sa.Column(
            "consulted_document_ids",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "answer_events",
        sa.Column("gap_reason", sa.String(length=16), nullable=True),
    )
    op.create_check_constraint(
        "ck_answer_events_consulted_document_ids",
        "answer_events",
        "jsonb_typeof(consulted_document_ids) = 'array' "
        "AND jsonb_array_length(consulted_document_ids) <= 10",
    )
    op.create_check_constraint(
        "ck_answer_events_gap_reason",
        "answer_events",
        "gap_reason IS NULL OR (abstained AND gap_reason IN "
        "('no_sources', 'not_found', 'checks', 'not_relevant'))",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_answer_events_gap_reason", "answer_events", type_="check"
    )
    op.drop_constraint(
        "ck_answer_events_consulted_document_ids", "answer_events", type_="check"
    )
    op.drop_column("answer_events", "gap_reason")
    op.drop_column("answer_events", "consulted_document_ids")
