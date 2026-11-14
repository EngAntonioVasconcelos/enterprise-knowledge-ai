"""Add the organization directory.

Revision ID: e2b8c4f7a9d1
Revises: d9a3f6b2e8c5
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e2b8c4f7a9d1"
down_revision: Union[str, Sequence[str], None] = "d9a3f6b2e8c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Members may see who their colleagues are and what role they hold, but
    # not their e-mail addresses. Row-level security filters rows, not
    # columns, so this view of colleagues is a function that returns only the
    # columns a member may see. Viewers and outsiders get no rows.
    op.execute("""
        CREATE FUNCTION app_private.organization_directory(
            p_organization_id uuid
        )
        RETURNS TABLE (user_id uuid, full_name text, role text)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
            SELECT u.id, u.full_name::text, m.role::text
            FROM public.organization_memberships AS m
            JOIN public.users AS u ON u.id = m.user_id
            WHERE m.organization_id = p_organization_id
              AND m.is_active
              AND u.is_active
              AND app_private.has_authenticated_context()
              AND EXISTS (
                  SELECT 1
                  FROM public.organization_memberships AS caller
                  WHERE caller.organization_id = p_organization_id
                    AND caller.user_id =
                        NULLIF(current_setting('app.user_id', true), '')::uuid
                    AND caller.is_active
                    AND caller.role IN ('owner', 'admin', 'member')
              )
            ORDER BY u.full_name, u.id;
        $function$;

        ALTER FUNCTION app_private.organization_directory(uuid)
            OWNER TO eka_rls_helper;

        REVOKE ALL ON FUNCTION app_private.organization_directory(uuid)
            FROM PUBLIC;

        GRANT EXECUTE ON FUNCTION app_private.organization_directory(uuid)
            TO eka_runtime;
    """)


def downgrade() -> None:
    op.execute("""
        DROP FUNCTION app_private.organization_directory(uuid);
    """)
