"""Add data connections: the sources each organization connects.

Revision ID: d8b4f1a7c3e5
Revises: c6a2e9f4b1d7
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d8b4f1a7c3e5"
down_revision: Union[str, Sequence[str], None] = "c6a2e9f4b1d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "last_synced_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "disconnected_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_connections"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_data_connections_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_data_connections_created_by_user_id_users",
        ),
        sa.CheckConstraint(
            "kind IN ('documents', 'tabular', 'database', 'application')",
            name="ck_data_connections_kind",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'error', 'disconnected')",
            name="ck_data_connections_status",
        ),
        sa.CheckConstraint(
            "(status = 'disconnected') = (disconnected_at IS NOT NULL)",
            name="ck_data_connections_disconnected_at",
        ),
        sa.CheckConstraint(
            "provider ~ '^[a-z][a-z0-9_]{1,63}$'",
            name="ck_data_connections_provider",
        ),
        sa.CheckConstraint(
            "btrim(name) <> ''",
            name="ck_data_connections_name",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(settings) = 'object'",
            name="ck_data_connections_settings",
        ),
    )
    op.create_index(
        "uq_data_connections_active_name",
        "data_connections",
        ["organization_id", "name"],
        unique=True,
        postgresql_where=sa.text("status <> 'disconnected'"),
    )

    # The API manages the connections of organizations it manages and never
    # deletes one. The worker sees only the connections of the organization
    # of its current job, and changes only what a synchronization reports.
    op.execute("""
        REVOKE ALL ON public.data_connections FROM PUBLIC;

        GRANT SELECT, INSERT ON public.data_connections TO eka_runtime;
        GRANT UPDATE (name, status, settings, updated_at, disconnected_at)
            ON public.data_connections TO eka_runtime;

        GRANT SELECT ON public.data_connections TO eka_worker;
        GRANT UPDATE (status, last_synced_at, last_error, updated_at)
            ON public.data_connections TO eka_worker;

        ALTER TABLE public.data_connections ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.data_connections FORCE ROW LEVEL SECURITY;

        CREATE POLICY data_connections_select_policy
        ON public.data_connections
        FOR SELECT
        TO eka_runtime
        USING (app_private.can_manage_organization(organization_id));

        CREATE POLICY data_connections_insert_policy
        ON public.data_connections
        FOR INSERT
        TO eka_runtime
        WITH CHECK (
            app_private.can_manage_organization(organization_id)
            AND status = 'active'
            AND last_synced_at IS NULL
            AND last_error IS NULL
            AND disconnected_at IS NULL
            AND created_by_user_id =
                NULLIF(current_setting('app.user_id', true), '')::uuid
        );

        CREATE POLICY data_connections_update_policy
        ON public.data_connections
        FOR UPDATE
        TO eka_runtime
        USING (app_private.can_manage_organization(organization_id))
        WITH CHECK (app_private.can_manage_organization(organization_id));

        CREATE POLICY data_connections_worker_select_policy
        ON public.data_connections
        FOR SELECT
        TO eka_worker
        USING (
            organization_id =
                NULLIF(current_setting('app.organization_id', true), '')::uuid
        );

        CREATE POLICY data_connections_worker_update_policy
        ON public.data_connections
        FOR UPDATE
        TO eka_worker
        USING (
            organization_id =
                NULLIF(current_setting('app.organization_id', true), '')::uuid
        )
        WITH CHECK (
            organization_id =
                NULLIF(current_setting('app.organization_id', true), '')::uuid
        );

        CREATE TRIGGER trg_require_active_organization
        BEFORE INSERT ON public.data_connections
        FOR EACH ROW
        EXECUTE FUNCTION app_private.require_active_organization();
    """)

    # "disconnected" is final. Every change stamps updated_at, and
    # disconnecting stamps disconnected_at, whatever the caller sent.
    op.execute("""
        CREATE FUNCTION app_private.protect_data_connections()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF OLD.status = 'disconnected' THEN
                RAISE EXCEPTION
                    'a disconnected connection cannot change'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;

            NEW.updated_at := clock_timestamp();

            IF NEW.status = 'disconnected' THEN
                NEW.disconnected_at := clock_timestamp();
            ELSE
                NEW.disconnected_at := NULL;
            END IF;

            RETURN NEW;
        END;
        $function$;

        REVOKE ALL ON FUNCTION app_private.protect_data_connections()
            FROM PUBLIC;

        CREATE TRIGGER trg_protect_data_connections
        BEFORE UPDATE ON public.data_connections
        FOR EACH ROW
        EXECUTE FUNCTION app_private.protect_data_connections();
    """)

    # Connections are part of the audit trail: who connected what, renamed,
    # paused or disconnected it. Settings changes are recorded without
    # their values.
    op.execute("""
        CREATE FUNCTION app_private.audit_connection_change()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                PERFORM app_private.record_audit_event(
                    NEW.organization_id, 'connection.created', 'connection',
                    NEW.id,
                    jsonb_build_object(
                        'provider', NEW.provider, 'name', NEW.name
                    )
                );
                RETURN NEW;
            END IF;

            IF NEW.name IS DISTINCT FROM OLD.name THEN
                PERFORM app_private.record_audit_event(
                    NEW.organization_id, 'connection.renamed', 'connection',
                    NEW.id,
                    jsonb_build_object('from', OLD.name, 'to', NEW.name)
                );
            END IF;

            IF NEW.status IS DISTINCT FROM OLD.status THEN
                PERFORM app_private.record_audit_event(
                    NEW.organization_id, 'connection.status_changed',
                    'connection', NEW.id,
                    jsonb_build_object('from', OLD.status, 'to', NEW.status)
                );
            END IF;

            IF NEW.settings IS DISTINCT FROM OLD.settings THEN
                PERFORM app_private.record_audit_event(
                    NEW.organization_id, 'connection.settings_changed',
                    'connection', NEW.id, '{}'::jsonb
                );
            END IF;

            RETURN NEW;
        END;
        $function$;

        ALTER FUNCTION app_private.audit_connection_change()
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.audit_connection_change()
            FROM PUBLIC;

        CREATE TRIGGER trg_audit_connection_change
        AFTER INSERT OR UPDATE ON public.data_connections
        FOR EACH ROW
        EXECUTE FUNCTION app_private.audit_connection_change();
    """)


def downgrade() -> None:
    op.drop_table("data_connections")

    op.execute("""
        DROP FUNCTION app_private.audit_connection_change();
        DROP FUNCTION app_private.protect_data_connections();
    """)
