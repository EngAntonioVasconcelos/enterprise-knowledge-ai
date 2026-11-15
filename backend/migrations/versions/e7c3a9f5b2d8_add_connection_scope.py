"""A connection's scope can keep roles out of its documents.

Revision ID: e7c3a9f5b2d8
Revises: d4a1e7b3c8f2

Owners and Admins may restrict a connection to some roles
(settings.scope.roles, app/services/connection_scope.py). A person reads
a document when the source allows it AND the scope lets their role in:
the scope only ever removes readers. Changing a person's role, or the
scope, takes effect at once.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e7c3a9f5b2d8"
down_revision: Union[str, Sequence[str], None] = "d4a1e7b3c8f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Same rule as migration a2d7c4e9f1b6.
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


def role_scope(role: str) -> str:
    """True when the connection's scope lets this role in."""
    return f"""
        (NOT jsonb_exists(
             COALESCE(c.settings -> 'scope', '{{}}'::jsonb), 'roles')
         OR jsonb_exists(c.settings -> 'scope' -> 'roles', {role}))
    """


def functions(member_role: str, membership_role: str, scope_changed: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION app_private.resolve_document_access(
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
              AND ({MATCHES})
              AND {membership_role};

            GET DIAGNOSTICS readers = ROW_COUNT;
            RETURN readers;
        END;
        $function$;

        CREATE OR REPLACE FUNCTION app_private.refresh_member_document_access()
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
                  AND ({MATCHES})
                  AND {member_role};
            END IF;

            RETURN NULL;
        END;
        $function$;

        CREATE OR REPLACE FUNCTION
            app_private.refresh_connection_document_access()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF (OLD.settings ->> 'link_sharing_grants_organization')
               IS NOT DISTINCT FROM
               (NEW.settings ->> 'link_sharing_grants_organization')
               AND NOT ({scope_changed}) THEN
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
              AND ({MATCHES})
              AND {membership_role};

            RETURN NULL;
        END;
        $function$;

        ALTER FUNCTION app_private.resolve_document_access(uuid)
            OWNER TO eka_rls_helper;
        ALTER FUNCTION app_private.refresh_member_document_access()
            OWNER TO eka_rls_helper;
        ALTER FUNCTION app_private.refresh_connection_document_access()
            OWNER TO eka_rls_helper;
    """


def member_trigger(columns: str) -> str:
    return f"""
        DROP TRIGGER trg_refresh_member_document_access
            ON public.organization_memberships;
        CREATE TRIGGER trg_refresh_member_document_access
        AFTER INSERT OR UPDATE OF {columns} ON public.organization_memberships
        FOR EACH ROW
        EXECUTE FUNCTION app_private.refresh_member_document_access();
    """


def upgrade() -> None:
    op.execute(
        functions(
            member_role=role_scope("NEW.role"),
            membership_role=role_scope("m.role"),
            scope_changed=(
                "(OLD.settings -> 'scope' -> 'roles') IS DISTINCT FROM "
                "(NEW.settings -> 'scope' -> 'roles')"
            ),
        )
    )
    # A new role can open or close documents of scoped connections.
    op.execute(member_trigger("is_active, role"))


def downgrade() -> None:
    op.execute(member_trigger("is_active"))
    op.execute(
        functions(member_role="TRUE", membership_role="TRUE", scope_changed="FALSE")
    )
