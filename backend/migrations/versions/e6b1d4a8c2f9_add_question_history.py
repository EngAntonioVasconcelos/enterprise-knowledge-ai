"""Question history: each person's own questions and answers (AK-6).

Each person reads and deletes only their own rows; nobody else in the
organization (owners and admins included) can read them. The organization
decides how long they are kept (history_retention_days: 0 keeps nothing),
and the worker deletes what is older.

Revision ID: e6b1d4a8c2f9
Revises: d2f7a3c9e5b1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e6b1d4a8c2f9"
down_revision: Union[str, Sequence[str], None] = "d2f7a3c9e5b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CURRENT_USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "history_retention_days",
            sa.Integer(),
            server_default=sa.text("90"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_organizations_history_retention_days",
        "organizations",
        "history_retention_days IN (0, 30, 90, 365)",
    )

    op.create_table(
        "question_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("abstained", sa.Boolean(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column(
            "sources",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_question_history"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_question_history_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_question_history_user_id_users",
        ),
        sa.CheckConstraint(
            "char_length(question) BETWEEN 1 AND 500",
            name="ck_question_history_question",
        ),
        sa.CheckConstraint(
            "char_length(answer) <= 20000",
            name="ck_question_history_answer",
        ),
        sa.CheckConstraint(
            "language IN ('pt', 'en', 'fr')",
            name="ck_question_history_language",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(sources) = 'array'",
            name="ck_question_history_sources",
        ),
    )
    op.create_index(
        "ix_question_history_owner_created",
        "question_history",
        ["organization_id", "user_id", "created_at"],
    )
    op.create_index(
        "ix_question_history_created",
        "question_history",
        ["created_at"],
    )

    # The person who asked is the only reader. A row is written for the
    # caller, in an organization the caller belongs to, and only while the
    # organization keeps a history. Rows are never changed.
    op.execute(f"""
        REVOKE ALL ON public.question_history FROM PUBLIC;

        GRANT SELECT, INSERT, DELETE ON public.question_history
            TO eka_runtime;
        GRANT SELECT, DELETE ON public.question_history TO eka_rls_helper;

        ALTER TABLE public.question_history ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.question_history FORCE ROW LEVEL SECURITY;

        CREATE POLICY question_history_select_policy
        ON public.question_history
        FOR SELECT
        TO eka_runtime
        USING (
            user_id = {CURRENT_USER}
            AND app_private.has_active_membership(organization_id)
        );

        CREATE POLICY question_history_insert_policy
        ON public.question_history
        FOR INSERT
        TO eka_runtime
        WITH CHECK (
            user_id = {CURRENT_USER}
            AND app_private.has_active_membership(organization_id)
            AND EXISTS (
                SELECT 1
                FROM public.organizations AS o
                WHERE o.id = organization_id
                  AND o.history_retention_days > 0
            )
        );

        CREATE POLICY question_history_delete_policy
        ON public.question_history
        FOR DELETE
        TO eka_runtime
        USING (user_id = {CURRENT_USER});

        CREATE TRIGGER trg_require_active_organization
        BEFORE INSERT ON public.question_history
        FOR EACH ROW
        EXECUTE FUNCTION app_private.require_active_organization();
    """)

    # The worker deletes what each organization no longer keeps. It cannot
    # read the rows: the function deletes and returns only a count.
    op.execute("""
        CREATE FUNCTION app_private.purge_expired_questions()
        RETURNS integer
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        DECLARE
            removed integer;
        BEGIN
            DELETE FROM public.question_history AS q
            USING public.organizations AS o
            WHERE o.id = q.organization_id
              AND q.created_at < clock_timestamp()
                  - make_interval(days => o.history_retention_days);
            GET DIAGNOSTICS removed = ROW_COUNT;
            RETURN removed;
        END;
        $function$;

        ALTER FUNCTION app_private.purge_expired_questions()
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.purge_expired_questions()
            FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION app_private.purge_expired_questions()
            TO eka_worker;
    """)

    # How long questions are kept is recorded in the audit log.
    op.execute("""
        CREATE FUNCTION app_private.audit_history_retention_change()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF NEW.history_retention_days
               IS DISTINCT FROM OLD.history_retention_days
            THEN
                PERFORM app_private.record_audit_event(
                    NEW.id, 'organization.history_retention_changed',
                    'organization', NEW.id,
                    jsonb_build_object(
                        'from', OLD.history_retention_days,
                        'to', NEW.history_retention_days
                    )
                );
            END IF;
            RETURN NEW;
        END;
        $function$;

        ALTER FUNCTION app_private.audit_history_retention_change()
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.audit_history_retention_change()
            FROM PUBLIC;

        CREATE TRIGGER trg_audit_history_retention_change
        AFTER UPDATE OF history_retention_days ON public.organizations
        FOR EACH ROW
        EXECUTE FUNCTION app_private.audit_history_retention_change();
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER trg_audit_history_retention_change
            ON public.organizations;
        DROP FUNCTION app_private.audit_history_retention_change();
        DROP FUNCTION app_private.purge_expired_questions();
    """)
    op.drop_index("ix_question_history_created", table_name="question_history")
    op.drop_index(
        "ix_question_history_owner_created", table_name="question_history"
    )
    op.drop_table("question_history")
    op.drop_constraint(
        "ck_organizations_history_retention_days",
        "organizations",
        type_="check",
    )
    op.drop_column("organizations", "history_retention_days")
