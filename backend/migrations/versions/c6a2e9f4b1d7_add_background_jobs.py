"""Add the background job queue and the eka_worker role that runs it.

Revision ID: c6a2e9f4b1d7
Revises: b3f8d2a6c9e4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c6a2e9f4b1d7"
down_revision: Union[str, Sequence[str], None] = "b3f8d2a6c9e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACTIVE = "status IN ('queued', 'running') AND dedupe_key IS NOT NULL"


def upgrade() -> None:
    # Capability role of the worker. The login that runs it is provisioned
    # separately and switches to this role with SET ROLE.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_catalog.pg_roles
                WHERE rolname = 'eka_worker'
            ) THEN
                CREATE ROLE eka_worker
                    NOLOGIN
                    NOSUPERUSER
                    NOCREATEDB
                    NOCREATEROLE
                    NOREPLICATION
                    NOBYPASSRLS;
            END IF;

            ALTER ROLE eka_worker
                NOLOGIN
                NOSUPERUSER
                NOCREATEDB
                NOCREATEROLE
                NOREPLICATION
                NOBYPASSRLS;
        END;
        $$;

        REVOKE eka_worker FROM eka_runtime;
    """)

    op.create_table(
        "background_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("dedupe_key", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default=sa.text("5"),
            nullable=False,
        ),
        sa.Column(
            "run_after", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("locked_by", sa.String(length=200), nullable=True),
        sa.Column(
            "locked_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "finished_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.PrimaryKeyConstraint("id", name="pk_background_jobs"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_background_jobs_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_background_jobs_created_by_user_id_users",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', "
            "'cancelled')",
            name="ck_background_jobs_status",
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND max_attempts >= 1",
            name="ck_background_jobs_attempts",
        ),
        sa.CheckConstraint(
            "kind ~ '^[a-z][a-z0-9_.]{1,63}$'",
            name="ck_background_jobs_kind",
        ),
    )
    op.create_index(
        "uq_background_jobs_active_dedupe",
        "background_jobs",
        ["organization_id", "kind", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
    )
    op.create_index(
        "ix_background_jobs_status_run_after",
        "background_jobs",
        ["status", "run_after"],
    )

    # The API enqueues and reads the jobs of organizations it manages; it
    # never claims or finishes one. The worker reads every job and changes
    # only the columns that track a run.
    op.execute("""
        REVOKE ALL ON public.background_jobs FROM PUBLIC;

        GRANT SELECT, INSERT ON public.background_jobs TO eka_runtime;

        GRANT USAGE ON SCHEMA public TO eka_worker;
        GRANT SELECT ON public.background_jobs TO eka_worker;
        GRANT UPDATE (
            status, attempts, run_after, locked_by, locked_at,
            last_error, finished_at
        ) ON public.background_jobs TO eka_worker;

        ALTER TABLE public.background_jobs ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.background_jobs FORCE ROW LEVEL SECURITY;

        CREATE POLICY background_jobs_select_policy
        ON public.background_jobs
        FOR SELECT
        TO eka_runtime
        USING (app_private.can_manage_organization(organization_id));

        CREATE POLICY background_jobs_insert_policy
        ON public.background_jobs
        FOR INSERT
        TO eka_runtime
        WITH CHECK (
            app_private.can_manage_organization(organization_id)
            AND status = 'queued'
            AND attempts = 0
            AND locked_by IS NULL
            AND locked_at IS NULL
            AND finished_at IS NULL
            AND last_error IS NULL
            AND created_by_user_id =
                NULLIF(current_setting('app.user_id', true), '')::uuid
        );

        CREATE POLICY background_jobs_worker_select_policy
        ON public.background_jobs
        FOR SELECT
        TO eka_worker
        USING (true);

        CREATE POLICY background_jobs_worker_update_policy
        ON public.background_jobs
        FOR UPDATE
        TO eka_worker
        USING (true)
        WITH CHECK (true);

        CREATE TRIGGER trg_require_active_organization
        BEFORE INSERT ON public.background_jobs
        FOR EACH ROW
        EXECUTE FUNCTION app_private.require_active_organization();
    """)

    # A job moves forward only: queued -> running -> succeeded or failed,
    # back to queued for a retry, or queued -> cancelled. A finished job
    # never changes again.
    op.execute("""
        CREATE FUNCTION app_private.protect_background_jobs()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF OLD.status IN ('succeeded', 'failed', 'cancelled') THEN
                RAISE EXCEPTION
                    'a finished job cannot change'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;

            IF NEW.status IS DISTINCT FROM OLD.status
               AND NOT (
                   (OLD.status = 'queued'
                    AND NEW.status IN ('running', 'cancelled'))
                   OR (OLD.status = 'running'
                       AND NEW.status IN ('succeeded', 'failed', 'queued'))
               ) THEN
                RAISE EXCEPTION
                    'invalid job status transition'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;

            IF NEW.attempts < OLD.attempts THEN
                RAISE EXCEPTION
                    'job attempts cannot decrease'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;

            RETURN NEW;
        END;
        $function$;

        REVOKE ALL ON FUNCTION app_private.protect_background_jobs()
            FROM PUBLIC;

        CREATE TRIGGER trg_protect_background_jobs
        BEFORE UPDATE ON public.background_jobs
        FOR EACH ROW
        EXECUTE FUNCTION app_private.protect_background_jobs();
    """)


def downgrade() -> None:
    op.drop_table("background_jobs")

    op.execute("""
        DROP FUNCTION app_private.protect_background_jobs();
        REVOKE USAGE ON SCHEMA public FROM eka_worker;
    """)
