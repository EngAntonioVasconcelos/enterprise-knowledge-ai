"""Where each document comes from and who can see it (AL-9).

Document permissions are read only by the worker, on purpose. The
documents list now also says, for each document the caller can already
open, its source and the kind of sharing: the whole organization, only
the caller, chosen people (uploads) or as at the source (Drive). Never the
names or the number of people, so nobody learns whom a colleague shared a
file with. app_private.document_audiences answers that and nothing else.

Revision ID: d9a3f6c2e8b1
Revises: c2f8e5a1d7b3
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d9a3f6c2e8b1"
down_revision: Union[str, Sequence[str], None] = "c2f8e5a1d7b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION app_private.document_audiences(p_organization_id uuid)
        RETURNS TABLE (
            document_id uuid,
            provider text,
            connection_name text,
            audience text
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
            SELECT
                d.id,
                c.provider::text,
                c.name::text,
                CASE
                    WHEN bool_or(
                        p.principal_type = 'organization'
                        OR (p.principal_type = 'anyone'
                            AND COALESCE(
                                (c.settings ->> 'link_sharing_grants_organization')::boolean,
                                false
                            ))
                    ) THEN 'organization'
                    -- One person and no wider grant: the caller, who can open it.
                    WHEN count(p.document_id) FILTER (WHERE p.principal_type = 'user') = 1
                        AND count(p.document_id) FILTER (
                            WHERE p.principal_type IN ('group', 'domain', 'anyone')
                        ) = 0
                    THEN 'only_you'
                    WHEN c.provider = 'file_upload' THEN 'people'
                    ELSE 'source'
                END
            FROM public.document_access AS a
            JOIN public.documents AS d ON d.id = a.document_id
            JOIN public.data_connections AS c ON c.id = d.connection_id
            LEFT JOIN public.document_permissions AS p ON p.document_id = d.id
            WHERE a.user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
              AND a.organization_id = p_organization_id
              AND d.status <> 'removed'
              AND app_private.has_active_membership(p_organization_id)
            GROUP BY d.id, c.provider, c.name, c.settings
        $function$;

        ALTER FUNCTION app_private.document_audiences(uuid) OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.document_audiences(uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION app_private.document_audiences(uuid) TO eka_runtime;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION app_private.document_audiences(uuid);")
