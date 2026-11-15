"""Source permissions on documents: every read is filtered by them.

Revision ID: a2d7c4e9f1b6
Revises: f3a8c6e1b9d4

Permission-aware AI: a person sees, searches and gets answers only from
documents they could open at the source. This holds for owners and admins
too (decision of 2026-11-15): even a title can reveal too much. Managers
get counts, not titles.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2d7c4e9f1b6"
down_revision: Union[str, Sequence[str], None] = "f3a8c6e1b9d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CURRENT_USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"
WORKER_ORGANIZATION = (
    "organization_id = "
    "NULLIF(current_setting('app.organization_id', true), '')::uuid"
)

# Who a permission row lets in, for a user u of the document's
# organization (d) and its connection (c). Groups are not resolved until
# group membership is synchronized: unknown means no access.
MATCHES = """
    (p.principal_type = 'user' AND p.principal = lower(u.email))
    OR (p.principal_type = 'domain'
        AND p.principal = split_part(lower(u.email), chr(64), 2))
    OR p.principal_type = 'organization'
    OR (p.principal_type = 'anyone'
        AND COALESCE(
            (c.settings ->> 'link_sharing_grants_organization')::boolean,
            false
        ))
"""

PREVIOUS_DOCUMENTS_POLICY = """
    CREATE POLICY documents_select_policy
    ON public.documents
    FOR SELECT
    TO eka_runtime
    USING (app_private.can_manage_organization(organization_id));

    CREATE POLICY document_versions_select_policy
    ON public.document_versions
    FOR SELECT
    TO eka_runtime
    USING (app_private.can_manage_organization(organization_id));
"""


def upgrade() -> None:
    op.create_table(
        "document_permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("principal_type", sa.String(length=16), nullable=False),
        sa.Column("principal", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_permissions"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_document_permissions_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_document_permissions_organization_id_organizations",
        ),
        sa.UniqueConstraint(
            "document_id",
            "principal_type",
            "principal",
            name="uq_document_permissions_principal",
        ),
        sa.CheckConstraint(
            "principal_type IN ('user', 'group', 'domain', 'anyone', "
            "'organization')",
            name="ck_document_permissions_principal_type",
        ),
        sa.CheckConstraint(
            "role IN ('reader', 'commenter', 'writer', 'owner')",
            name="ck_document_permissions_role",
        ),
        sa.CheckConstraint(
            "principal = lower(principal)",
            name="ck_document_permissions_principal_lowercase",
        ),
        sa.CheckConstraint(
            "(principal_type IN ('anyone', 'organization')) = "
            "(principal = '')",
            name="ck_document_permissions_principal_present",
        ),
    )
    op.create_index(
        "ix_document_permissions_lookup",
        "document_permissions",
        ["organization_id", "principal_type", "principal"],
    )

    op.create_table(
        "document_access",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint(
            "document_id", "user_id", name="pk_document_access"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_document_access_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_document_access_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_document_access_organization_id_organizations",
        ),
    )
    op.create_index(
        "ix_document_access_user_organization",
        "document_access",
        ["user_id", "organization_id"],
    )

    # The worker replaces a document's permissions at each sync; only
    # database functions write the resolved readers. The API reads its own
    # access rows, which is what filters documents and versions.
    op.execute(f"""
        REVOKE ALL ON public.document_permissions FROM PUBLIC;
        REVOKE ALL ON public.document_access FROM PUBLIC;

        GRANT SELECT, INSERT, DELETE ON public.document_permissions
            TO eka_worker;
        GRANT SELECT ON public.document_access TO eka_runtime;

        GRANT SELECT ON public.data_connections TO eka_rls_helper;
        GRANT SELECT ON public.document_permissions TO eka_rls_helper;
        GRANT SELECT, INSERT, DELETE ON public.document_access
            TO eka_rls_helper;

        ALTER TABLE public.document_permissions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.document_permissions FORCE ROW LEVEL SECURITY;
        ALTER TABLE public.document_access ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.document_access FORCE ROW LEVEL SECURITY;

        CREATE POLICY document_permissions_worker_policy
        ON public.document_permissions
        FOR ALL
        TO eka_worker
        USING ({WORKER_ORGANIZATION})
        WITH CHECK (
            {WORKER_ORGANIZATION}
            AND EXISTS (
                SELECT 1
                FROM public.documents AS d
                WHERE d.id = document_id
                  AND d.organization_id = document_permissions.organization_id
            )
        );

        CREATE POLICY document_access_select_policy
        ON public.document_access
        FOR SELECT
        TO eka_runtime
        USING (user_id = {CURRENT_USER});

        DROP POLICY documents_select_policy ON public.documents;
        DROP POLICY document_versions_select_policy
            ON public.document_versions;

        CREATE POLICY documents_select_policy
        ON public.documents
        FOR SELECT
        TO eka_runtime
        USING (
            EXISTS (
                SELECT 1
                FROM public.document_access AS a
                WHERE a.document_id = documents.id
                  AND a.user_id = {CURRENT_USER}
            )
        );

        CREATE POLICY document_versions_select_policy
        ON public.document_versions
        FOR SELECT
        TO eka_runtime
        USING (
            EXISTS (
                SELECT 1
                FROM public.document_access AS a
                WHERE a.document_id = document_versions.document_id
                  AND a.user_id = {CURRENT_USER}
            )
        );
    """)

    op.execute(f"""
        CREATE FUNCTION app_private.resolve_document_access(
            p_document_id uuid
        )
        RETURNS integer
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        DECLARE
            document_organization uuid;
            readers integer;
        BEGIN
            SELECT organization_id INTO document_organization
            FROM public.documents
            WHERE id = p_document_id;

            IF document_organization IS NULL THEN
                RAISE EXCEPTION 'document not found'
                    USING ERRCODE = 'no_data_found';
            END IF;

            -- The worker may resolve only the organization of its job.
            IF document_organization IS DISTINCT FROM
               NULLIF(current_setting('app.organization_id', true), '')::uuid
            THEN
                RAISE EXCEPTION
                    'document belongs to another organization'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            DELETE FROM public.document_access
            WHERE document_id = p_document_id;

            INSERT INTO public.document_access (
                document_id, user_id, organization_id, created_at
            )
            SELECT DISTINCT d.id, u.id, d.organization_id, clock_timestamp()
            FROM public.documents AS d
            JOIN public.data_connections AS c ON c.id = d.connection_id
            JOIN public.organization_memberships AS m
              ON m.organization_id = d.organization_id AND m.is_active
            JOIN public.users AS u ON u.id = m.user_id AND u.is_active
            JOIN public.document_permissions AS p ON p.document_id = d.id
            WHERE d.id = p_document_id
              AND ({MATCHES});

            GET DIAGNOSTICS readers = ROW_COUNT;
            RETURN readers;
        END;
        $function$;

        ALTER FUNCTION app_private.resolve_document_access(uuid)
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.resolve_document_access(uuid)
            FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION app_private.resolve_document_access(uuid)
            TO eka_worker;
        GRANT USAGE ON SCHEMA app_private TO eka_worker;
    """)

    # Membership changes take effect at once, without waiting for a sync:
    # leaving removes every access in that organization; joining (or
    # coming back) grants what the stored permissions already allow.
    op.execute(f"""
        CREATE FUNCTION app_private.refresh_member_document_access()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            DELETE FROM public.document_access
            WHERE organization_id = NEW.organization_id
              AND user_id = NEW.user_id;

            IF NEW.is_active THEN
                INSERT INTO public.document_access (
                    document_id, user_id, organization_id, created_at
                )
                SELECT DISTINCT d.id, u.id, d.organization_id,
                                clock_timestamp()
                FROM public.documents AS d
                JOIN public.data_connections AS c ON c.id = d.connection_id
                JOIN public.users AS u ON u.id = NEW.user_id AND u.is_active
                JOIN public.document_permissions AS p
                  ON p.document_id = d.id
                WHERE d.organization_id = NEW.organization_id
                  AND ({MATCHES});
            END IF;

            RETURN NULL;
        END;
        $function$;

        ALTER FUNCTION app_private.refresh_member_document_access()
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.refresh_member_document_access()
            FROM PUBLIC;

        CREATE TRIGGER trg_refresh_member_document_access
        AFTER INSERT OR UPDATE OF is_active ON public.organization_memberships
        FOR EACH ROW
        EXECUTE FUNCTION app_private.refresh_member_document_access();

        -- Changing whether link sharing counts re-resolves the
        -- connection's documents.
        CREATE FUNCTION app_private.refresh_connection_document_access()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF (OLD.settings ->> 'link_sharing_grants_organization')
               IS NOT DISTINCT FROM
               (NEW.settings ->> 'link_sharing_grants_organization') THEN
                RETURN NULL;
            END IF;

            DELETE FROM public.document_access AS a
            USING public.documents AS d
            WHERE d.id = a.document_id AND d.connection_id = NEW.id;

            INSERT INTO public.document_access (
                document_id, user_id, organization_id, created_at
            )
            SELECT DISTINCT d.id, u.id, d.organization_id, clock_timestamp()
            FROM public.documents AS d
            JOIN public.data_connections AS c ON c.id = d.connection_id
            JOIN public.organization_memberships AS m
              ON m.organization_id = d.organization_id AND m.is_active
            JOIN public.users AS u ON u.id = m.user_id AND u.is_active
            JOIN public.document_permissions AS p ON p.document_id = d.id
            WHERE d.connection_id = NEW.id
              AND ({MATCHES});

            RETURN NULL;
        END;
        $function$;

        ALTER FUNCTION app_private.refresh_connection_document_access()
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION
            app_private.refresh_connection_document_access()
            FROM PUBLIC;

        CREATE TRIGGER trg_refresh_connection_document_access
        AFTER UPDATE OF settings ON public.data_connections
        FOR EACH ROW
        EXECUTE FUNCTION app_private.refresh_connection_document_access();
    """)

    # Managers see numbers, not titles.
    op.execute("""
        CREATE FUNCTION app_private.document_statistics(
            p_organization_id uuid
        )
        RETURNS TABLE (status text, documents bigint)
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF NOT app_private.can_manage_organization(p_organization_id)
            THEN
                RAISE EXCEPTION
                    'only owners and admins see document statistics'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            RETURN QUERY
            SELECT d.status::text, count(*)
            FROM public.documents AS d
            WHERE d.organization_id = p_organization_id
            GROUP BY d.status;
        END;
        $function$;

        ALTER FUNCTION app_private.document_statistics(uuid)
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.document_statistics(uuid)
            FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION app_private.document_statistics(uuid)
            TO eka_runtime;
    """)


def downgrade() -> None:
    op.execute(f"""
        DROP FUNCTION app_private.document_statistics(uuid);

        DROP TRIGGER trg_refresh_connection_document_access
            ON public.data_connections;
        DROP FUNCTION app_private.refresh_connection_document_access();
        DROP TRIGGER trg_refresh_member_document_access
            ON public.organization_memberships;
        DROP FUNCTION app_private.refresh_member_document_access();

        REVOKE USAGE ON SCHEMA app_private FROM eka_worker;
        DROP FUNCTION app_private.resolve_document_access(uuid);

        DROP POLICY documents_select_policy ON public.documents;
        DROP POLICY document_versions_select_policy
            ON public.document_versions;
        {PREVIOUS_DOCUMENTS_POLICY}

        REVOKE SELECT ON public.data_connections FROM eka_rls_helper;
    """)

    op.drop_table("document_access")
    op.drop_table("document_permissions")
