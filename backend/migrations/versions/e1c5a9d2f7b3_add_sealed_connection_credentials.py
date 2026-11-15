"""Add organization keys and sealed connection credentials (ADR-007).

Revision ID: e1c5a9d2f7b3
Revises: d8b4f1a7c3e5
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1c5a9d2f7b3"
down_revision: Union[str, Sequence[str], None] = "d8b4f1a7c3e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


WORKER_ORGANIZATION = (
    "organization_id = "
    "NULLIF(current_setting('app.organization_id', true), '')::uuid"
)


def upgrade() -> None:
    op.create_table(
        "organization_keys",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sealed_private_key", sa.LargeBinary(), nullable=False),
        sa.Column(
            "master_key_fingerprint", sa.String(length=64), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", name="pk_organization_keys"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_organization_keys_organization_id_organizations",
        ),
        sa.CheckConstraint(
            "octet_length(public_key) = 32",
            name="ck_organization_keys_public_key",
        ),
    )

    op.create_table(
        "connection_credentials",
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("sealed", sa.LargeBinary(), nullable=False),
        sa.Column(
            "organization_key_fingerprint",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint(
            "connection_id", name="pk_connection_credentials"
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["data_connections.id"],
            ondelete="CASCADE",
            name="fk_connection_credentials_connection_id_data_connections",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_connection_credentials_organization_id_organizations",
        ),
        sa.CheckConstraint(
            "octet_length(sealed) > 60",
            name="ck_connection_credentials_sealed",
        ),
    )

    # The API may see that a key or a credential exists, never the sealed
    # bytes: column privileges leave them out. Nobody updates a key, and
    # nobody deletes anything directly.
    op.execute(f"""
        REVOKE ALL ON public.organization_keys FROM PUBLIC;
        REVOKE ALL ON public.connection_credentials FROM PUBLIC;

        GRANT SELECT (
            organization_id, public_key, master_key_fingerprint, created_at
        ) ON public.organization_keys TO eka_runtime;
        GRANT INSERT ON public.organization_keys TO eka_runtime;

        GRANT SELECT (
            connection_id, organization_id, organization_key_fingerprint,
            created_at, updated_at
        ) ON public.connection_credentials TO eka_runtime;
        GRANT INSERT ON public.connection_credentials TO eka_runtime;
        GRANT UPDATE (sealed, organization_key_fingerprint, updated_at)
            ON public.connection_credentials TO eka_runtime;

        GRANT SELECT ON public.organization_keys TO eka_worker;
        GRANT SELECT ON public.connection_credentials TO eka_worker;

        GRANT SELECT, DELETE ON public.connection_credentials
            TO eka_rls_helper;

        ALTER TABLE public.organization_keys ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.organization_keys FORCE ROW LEVEL SECURITY;
        ALTER TABLE public.connection_credentials ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.connection_credentials FORCE ROW LEVEL SECURITY;

        CREATE POLICY organization_keys_select_policy
        ON public.organization_keys
        FOR SELECT
        TO eka_runtime
        USING (app_private.can_manage_organization(organization_id));

        CREATE POLICY organization_keys_insert_policy
        ON public.organization_keys
        FOR INSERT
        TO eka_runtime
        WITH CHECK (app_private.can_manage_organization(organization_id));

        CREATE POLICY organization_keys_worker_select_policy
        ON public.organization_keys
        FOR SELECT
        TO eka_worker
        USING ({WORKER_ORGANIZATION});

        CREATE POLICY connection_credentials_select_policy
        ON public.connection_credentials
        FOR SELECT
        TO eka_runtime
        USING (app_private.can_manage_organization(organization_id));

        CREATE POLICY connection_credentials_insert_policy
        ON public.connection_credentials
        FOR INSERT
        TO eka_runtime
        WITH CHECK (
            app_private.can_manage_organization(organization_id)
            AND EXISTS (
                SELECT 1
                FROM public.data_connections AS c
                WHERE c.id = connection_id
                  AND c.organization_id = connection_credentials.organization_id
                  AND c.status <> 'disconnected'
            )
        );

        CREATE POLICY connection_credentials_update_policy
        ON public.connection_credentials
        FOR UPDATE
        TO eka_runtime
        USING (app_private.can_manage_organization(organization_id))
        WITH CHECK (
            app_private.can_manage_organization(organization_id)
            AND EXISTS (
                SELECT 1
                FROM public.data_connections AS c
                WHERE c.id = connection_id
                  AND c.organization_id = connection_credentials.organization_id
                  AND c.status <> 'disconnected'
            )
        );

        CREATE POLICY connection_credentials_worker_select_policy
        ON public.connection_credentials
        FOR SELECT
        TO eka_worker
        USING ({WORKER_ORGANIZATION});

        CREATE TRIGGER trg_require_active_organization
        BEFORE INSERT ON public.organization_keys
        FOR EACH ROW
        EXECUTE FUNCTION app_private.require_active_organization();

        CREATE TRIGGER trg_require_active_organization
        BEFORE INSERT OR UPDATE ON public.connection_credentials
        FOR EACH ROW
        EXECUTE FUNCTION app_private.require_active_organization();
    """)

    # Disconnecting a source destroys its secret at once, whatever path
    # disconnected it. Setting, replacing and destroying a secret are
    # audited (never its content).
    op.execute("""
        CREATE FUNCTION app_private.destroy_disconnected_credentials()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            DELETE FROM public.connection_credentials
            WHERE connection_id = NEW.id;

            RETURN NULL;
        END;
        $function$;

        ALTER FUNCTION app_private.destroy_disconnected_credentials()
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.destroy_disconnected_credentials()
            FROM PUBLIC;

        CREATE TRIGGER trg_destroy_disconnected_credentials
        AFTER UPDATE OF status ON public.data_connections
        FOR EACH ROW
        WHEN (NEW.status = 'disconnected')
        EXECUTE FUNCTION app_private.destroy_disconnected_credentials();

        CREATE FUNCTION app_private.audit_credential_change()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        DECLARE
            target public.connection_credentials;
            action text;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                target := OLD;
                action := 'connection.credentials_destroyed';
            ELSIF TG_OP = 'UPDATE' THEN
                target := NEW;
                action := 'connection.credentials_replaced';
            ELSE
                target := NEW;
                action := 'connection.credentials_set';
            END IF;

            PERFORM app_private.record_audit_event(
                target.organization_id, action, 'connection',
                target.connection_id,
                jsonb_build_object(
                    'key', target.organization_key_fingerprint
                )
            );

            RETURN NULL;
        END;
        $function$;

        ALTER FUNCTION app_private.audit_credential_change()
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.audit_credential_change()
            FROM PUBLIC;

        CREATE TRIGGER trg_audit_credential_change
        AFTER INSERT OR UPDATE OR DELETE ON public.connection_credentials
        FOR EACH ROW
        EXECUTE FUNCTION app_private.audit_credential_change();
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER trg_destroy_disconnected_credentials
            ON public.data_connections;
        DROP FUNCTION app_private.destroy_disconnected_credentials();
    """)

    op.drop_table("connection_credentials")
    op.drop_table("organization_keys")

    op.execute("""
        DROP FUNCTION app_private.audit_credential_change();
    """)
