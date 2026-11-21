"""Anonymous answer events for the organization dashboard (AK-7).

One row per answer: the day, whether there was a safe answer, the language
and the cited documents. No person, no question, no answer text: the
dashboard never shows who asked or what. Owners and admins read the rows of
their organization; members write them; nobody changes them. Rows older
than a year are deleted by the worker.

Revision ID: f2c7a9e4b6d1
Revises: e6b1d4a8c2f9
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f2c7a9e4b6d1"
down_revision: Union[str, Sequence[str], None] = "e6b1d4a8c2f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "answer_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        # The day only: an exact time would say more than the dashboard needs.
        sa.Column(
            "answered_on",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
        sa.Column("abstained", sa.Boolean(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column(
            "cited_document_ids",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_answer_events"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_answer_events_organization_id_organizations",
        ),
        sa.CheckConstraint(
            "language IN ('pt', 'en', 'fr')",
            name="ck_answer_events_language",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(cited_document_ids) = 'array' "
            "AND jsonb_array_length(cited_document_ids) <= 10",
            name="ck_answer_events_cited_document_ids",
        ),
    )
    op.create_index(
        "ix_answer_events_organization_day",
        "answer_events",
        ["organization_id", "answered_on"],
    )

    op.execute("""
        REVOKE ALL ON public.answer_events FROM PUBLIC;

        GRANT SELECT, INSERT ON public.answer_events TO eka_runtime;
        GRANT SELECT, DELETE ON public.answer_events TO eka_rls_helper;

        ALTER TABLE public.answer_events ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.answer_events FORCE ROW LEVEL SECURITY;

        CREATE POLICY answer_events_select_policy
        ON public.answer_events
        FOR SELECT
        TO eka_runtime
        USING (app_private.can_manage_organization(organization_id));

        -- Written for today, by a member, in that member's organization.
        CREATE POLICY answer_events_insert_policy
        ON public.answer_events
        FOR INSERT
        TO eka_runtime
        WITH CHECK (
            app_private.has_active_membership(organization_id)
            AND answered_on = CURRENT_DATE
        );

        CREATE TRIGGER trg_require_active_organization
        BEFORE INSERT ON public.answer_events
        FOR EACH ROW
        EXECUTE FUNCTION app_private.require_active_organization();
    """)

    op.execute("""
        CREATE FUNCTION app_private.purge_old_answer_events()
        RETURNS integer
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        DECLARE
            removed integer;
        BEGIN
            DELETE FROM public.answer_events
            WHERE answered_on < CURRENT_DATE - 365;
            GET DIAGNOSTICS removed = ROW_COUNT;
            RETURN removed;
        END;
        $function$;

        ALTER FUNCTION app_private.purge_old_answer_events()
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.purge_old_answer_events()
            FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION app_private.purge_old_answer_events()
            TO eka_worker;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION app_private.purge_old_answer_events();")
    op.drop_index(
        "ix_answer_events_organization_day", table_name="answer_events"
    )
    op.drop_table("answer_events")
