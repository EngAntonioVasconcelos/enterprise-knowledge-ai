"""Protect identity tables with row-level security.

Revision ID: f1a4c7e93b28
Revises: e8f3b0d52a16
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f1a4c7e93b28"
down_revision: Union[str, Sequence[str], None] = "e8f3b0d52a16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The helper role reads both tables inside the visibility check and
    # writes them inside the provisioning function. It cannot log in.
    op.execute("""
        GRANT SELECT, INSERT
        ON public.users, public.authentication_identities
        TO eka_rls_helper;
    """)

    # A user row is visible to:
    #   1. the user themselves;
    #   2. the request that presented that user's verified identity, before
    #      the user id is known (this is how login resolves the account);
    #   3. owners and admins of an organization the user belongs to.
    op.execute("""
        CREATE FUNCTION app_private.can_view_user(p_user_id uuid)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
            SELECT
                (
                    app_private.has_authenticated_context()
                    AND p_user_id =
                        NULLIF(current_setting('app.user_id', true), '')::uuid
                )
                OR EXISTS (
                    SELECT 1
                    FROM public.authentication_identities AS i
                    WHERE i.user_id = p_user_id
                      AND i.issuer =
                          NULLIF(current_setting('app.auth_issuer', true), '')
                      AND i.subject =
                          NULLIF(current_setting('app.auth_subject', true), '')
                )
                OR (
                    app_private.has_authenticated_context()
                    AND EXISTS (
                        SELECT 1
                        FROM public.organization_memberships AS target
                        JOIN public.organization_memberships AS actor
                          ON actor.organization_id = target.organization_id
                        WHERE target.user_id = p_user_id
                          AND actor.user_id =
                              NULLIF(
                                  current_setting('app.user_id', true), ''
                              )::uuid
                          AND actor.is_active IS TRUE
                          AND actor.role IN ('owner', 'admin')
                    )
                );
        $function$;

        ALTER FUNCTION app_private.can_view_user(uuid)
            OWNER TO eka_rls_helper;

        REVOKE ALL ON FUNCTION app_private.can_view_user(uuid) FROM PUBLIC;

        GRANT EXECUTE ON FUNCTION app_private.can_view_user(uuid)
            TO eka_runtime;
    """)

    # Accounts and identities are created only here. The function trusts
    # the backend for two facts it cannot check itself: that the issuer and
    # subject in the transaction context come from a verified token, and
    # that the e-mail was verified by the identity provider. An existing
    # account is linked by that verified e-mail and by nothing else.
    op.execute("""
        CREATE FUNCTION app_private.provision_user(
            p_email text,
            p_full_name text
        )
        RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        DECLARE
            v_issuer text :=
                NULLIF(current_setting('app.auth_issuer', true), '');
            v_subject text :=
                NULLIF(current_setting('app.auth_subject', true), '');
            v_email text := lower(btrim(coalesce(p_email, '')));
            v_full_name text := btrim(coalesce(p_full_name, ''));
            v_user_id uuid;
            v_is_active boolean;
        BEGIN
            IF v_issuer IS NULL OR v_subject IS NULL THEN
                RAISE EXCEPTION
                    'an authenticated identity is required'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            IF v_email = '' OR v_full_name = '' THEN
                RAISE EXCEPTION
                    'email and full name are required'
                    USING ERRCODE = 'invalid_parameter_value';
            END IF;

            -- Serialize concurrent first logins of the same person.
            PERFORM pg_advisory_xact_lock(
                hashtextextended('provision-user:' || v_email, 0)
            );

            SELECT i.user_id, i.is_active AND u.is_active
            INTO v_user_id, v_is_active
            FROM public.authentication_identities AS i
            JOIN public.users AS u ON u.id = i.user_id
            WHERE i.issuer = v_issuer
              AND i.subject = v_subject;

            IF FOUND THEN
                IF NOT v_is_active THEN
                    RAISE EXCEPTION
                        'the account or identity is disabled'
                        USING ERRCODE = 'insufficient_privilege';
                END IF;

                RETURN v_user_id;
            END IF;

            SELECT u.id, u.is_active
            INTO v_user_id, v_is_active
            FROM public.users AS u
            WHERE u.email = v_email;

            IF FOUND THEN
                IF NOT v_is_active THEN
                    RAISE EXCEPTION
                        'the account or identity is disabled'
                        USING ERRCODE = 'insufficient_privilege';
                END IF;
            ELSE
                v_user_id := gen_random_uuid();

                INSERT INTO public.users (
                    id, email, full_name, is_active, created_at, updated_at
                )
                VALUES (
                    v_user_id, v_email, v_full_name, true, now(), now()
                );
            END IF;

            INSERT INTO public.authentication_identities (
                id, user_id, issuer, subject, is_active, created_at
            )
            VALUES (
                gen_random_uuid(), v_user_id, v_issuer, v_subject, true, now()
            );

            RETURN v_user_id;
        END;
        $function$;

        ALTER FUNCTION app_private.provision_user(text, text)
            OWNER TO eka_rls_helper;

        REVOKE ALL ON FUNCTION app_private.provision_user(text, text)
            FROM PUBLIC;

        GRANT EXECUTE ON FUNCTION app_private.provision_user(text, text)
            TO eka_runtime;
    """)

    op.execute("""
        ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.users FORCE ROW LEVEL SECURITY;

        CREATE POLICY users_select_policy
        ON public.users
        FOR SELECT
        TO PUBLIC
        USING (app_private.can_view_user(id));
    """)

    # Transitional: owners and admins can still create an account while
    # adding someone to their organization. This policy is removed when
    # invitations replace that flow; accounts will then be created only by
    # app_private.provision_user.
    op.execute("""
        CREATE POLICY users_insert_policy
        ON public.users
        FOR INSERT
        TO PUBLIC
        WITH CHECK (
            app_private.can_manage_organization(
                NULLIF(
                    current_setting('app.organization_id', true), ''
                )::uuid
            )
        );
    """)

    op.execute("""
        ALTER TABLE public.authentication_identities
            ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.authentication_identities
            FORCE ROW LEVEL SECURITY;

        CREATE POLICY authentication_identities_select_policy
        ON public.authentication_identities
        FOR SELECT
        TO PUBLIC
        USING (
            issuer = NULLIF(current_setting('app.auth_issuer', true), '')
            AND subject =
                NULLIF(current_setting('app.auth_subject', true), '')
        );
    """)

    # Nothing in the application updates an account or writes an identity
    # directly. Each privilege returns with the feature that needs it.
    op.execute("""
        REVOKE UPDATE ON public.users FROM eka_runtime;

        REVOKE INSERT, UPDATE
        ON public.authentication_identities
        FROM eka_runtime;
    """)


def downgrade() -> None:
    op.execute("""
        GRANT UPDATE ON public.users TO eka_runtime;

        GRANT INSERT, UPDATE
        ON public.authentication_identities
        TO eka_runtime;

        DROP POLICY authentication_identities_select_policy
            ON public.authentication_identities;

        ALTER TABLE public.authentication_identities
            NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE public.authentication_identities
            DISABLE ROW LEVEL SECURITY;

        DROP POLICY users_insert_policy ON public.users;
        DROP POLICY users_select_policy ON public.users;

        ALTER TABLE public.users NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE public.users DISABLE ROW LEVEL SECURITY;

        DROP FUNCTION app_private.provision_user(text, text);
        DROP FUNCTION app_private.can_view_user(uuid);

        REVOKE SELECT, INSERT
        ON public.users, public.authentication_identities
        FROM eka_rls_helper;
    """)
