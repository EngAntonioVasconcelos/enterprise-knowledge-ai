"""create_private_rls_helpers

Revision ID: 9a71c4d2e6b8
Revises: 33e00045f12e
"""

from typing import Sequence, Union

from alembic import op


revision: str = "9a71c4d2e6b8"
down_revision: Union[str, Sequence[str], None] = "33e00045f12e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create or normalize the cluster-wide, non-login helper role.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_catalog.pg_roles
                WHERE rolname = 'eka_rls_helper'
            ) THEN
                EXECUTE
                    'CREATE ROLE eka_rls_helper
                     NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                     NOREPLICATION BYPASSRLS';
            ELSE
                EXECUTE
                    'ALTER ROLE eka_rls_helper
                     NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                     NOREPLICATION BYPASSRLS';
            END IF;
        END
        $$;
    """)

    op.execute("""
        CREATE SCHEMA app_private AUTHORIZATION eka_rls_helper;
        REVOKE ALL ON SCHEMA app_private FROM PUBLIC;
        GRANT USAGE ON SCHEMA app_private TO eka_runtime;
        GRANT USAGE ON SCHEMA public TO eka_rls_helper;
        GRANT SELECT ON public.organizations,
                        public.organization_memberships
        TO eka_rls_helper;
    """)

    # This function only validates that the backend-established
    # transaction context contains the required identity attributes.
    op.execute("""
        CREATE FUNCTION app_private.has_authenticated_context()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SET search_path = pg_catalog
        AS $function$
            SELECT
                NULLIF(current_setting('app.auth_issuer', true), '') IS NOT NULL
                AND NULLIF(current_setting('app.auth_subject', true), '') IS NOT NULL
                AND NULLIF(current_setting('app.user_id', true), '') IS NOT NULL;
        $function$;
    """)

    # These functions read tenant tables through a narrowly privileged
    # SECURITY DEFINER role to avoid recursive membership RLS policies.
    op.execute("""
        CREATE FUNCTION app_private.has_active_membership(
            p_organization_id uuid
        )
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
            SELECT
                app_private.has_authenticated_context()
                AND EXISTS (
                    SELECT 1
                    FROM public.organization_memberships AS m
                    WHERE m.organization_id = p_organization_id
                      AND m.user_id =
                          NULLIF(current_setting('app.user_id', true), '')::uuid
                      AND m.is_active IS TRUE
                );
        $function$;
    """)

    op.execute("""
        CREATE FUNCTION app_private.can_manage_organization(
            p_organization_id uuid
        )
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
            SELECT
                app_private.has_authenticated_context()
                AND EXISTS (
                    SELECT 1
                    FROM public.organization_memberships AS m
                    WHERE m.organization_id = p_organization_id
                      AND m.user_id =
                          NULLIF(current_setting('app.user_id', true), '')::uuid
                      AND m.is_active IS TRUE
                      AND m.role IN ('owner', 'admin')
                );
        $function$;
    """)

    op.execute("""
        CREATE FUNCTION app_private.is_bootstrap_creator(
            p_organization_id uuid
        )
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
            SELECT
                app_private.has_authenticated_context()
                AND EXISTS (
                    SELECT 1
                    FROM public.organizations AS o
                    WHERE o.id = p_organization_id
                      AND o.created_by_user_id =
                          NULLIF(current_setting('app.user_id', true), '')::uuid
                      AND NOT EXISTS (
                          SELECT 1
                          FROM public.organization_memberships AS m
                          WHERE m.organization_id = o.id
                      )
                );
        $function$;
    """)

    # Assign ownership to the non-login helper role.
    op.execute("""
        ALTER FUNCTION app_private.has_authenticated_context()
            OWNER TO eka_rls_helper;
        ALTER FUNCTION app_private.has_active_membership(uuid)
            OWNER TO eka_rls_helper;
        ALTER FUNCTION app_private.can_manage_organization(uuid)
            OWNER TO eka_rls_helper;
        ALTER FUNCTION app_private.is_bootstrap_creator(uuid)
            OWNER TO eka_rls_helper;
    """)

    # Remove default PUBLIC execution and grant only the required roles.
    op.execute("""
        REVOKE ALL ON FUNCTION app_private.has_authenticated_context()
            FROM PUBLIC;
        REVOKE ALL ON FUNCTION app_private.has_active_membership(uuid)
            FROM PUBLIC;
        REVOKE ALL ON FUNCTION app_private.can_manage_organization(uuid)
            FROM PUBLIC;
        REVOKE ALL ON FUNCTION app_private.is_bootstrap_creator(uuid)
            FROM PUBLIC;

        GRANT EXECUTE ON FUNCTION app_private.has_authenticated_context()
            TO eka_rls_helper, eka_runtime;
        GRANT EXECUTE ON FUNCTION app_private.has_active_membership(uuid)
            TO eka_runtime;
        GRANT EXECUTE ON FUNCTION app_private.can_manage_organization(uuid)
            TO eka_runtime;
        GRANT EXECUTE ON FUNCTION app_private.is_bootstrap_creator(uuid)
            TO eka_runtime;
    """)

    # The integration-test role is optional outside the test environment.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_catalog.pg_roles
                WHERE rolname = 'eka_test_runtime'
            ) THEN
                EXECUTE
                    'GRANT USAGE ON SCHEMA app_private TO eka_test_runtime';
                EXECUTE
                    'GRANT EXECUTE ON FUNCTION
                     app_private.has_authenticated_context()
                     TO eka_test_runtime';
                EXECUTE
                    'GRANT EXECUTE ON FUNCTION
                     app_private.has_active_membership(uuid)
                     TO eka_test_runtime';
                EXECUTE
                    'GRANT EXECUTE ON FUNCTION
                     app_private.can_manage_organization(uuid)
                     TO eka_test_runtime';
                EXECUTE
                    'GRANT EXECUTE ON FUNCTION
                     app_private.is_bootstrap_creator(uuid)
                     TO eka_test_runtime';
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.execute("""
        DROP FUNCTION IF EXISTS app_private.is_bootstrap_creator(uuid);
        DROP FUNCTION IF EXISTS app_private.can_manage_organization(uuid);
        DROP FUNCTION IF EXISTS app_private.has_active_membership(uuid);
        DROP FUNCTION IF EXISTS app_private.has_authenticated_context();

        REVOKE SELECT ON public.organizations,
                        public.organization_memberships
        FROM eka_rls_helper;

        REVOKE USAGE ON SCHEMA public FROM eka_rls_helper;

        DROP SCHEMA IF EXISTS app_private;
    """)
