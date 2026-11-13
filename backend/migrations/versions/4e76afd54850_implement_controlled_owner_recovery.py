"""Implement controlled organization owner recovery.

Revision ID: 4e76afd54850
Revises: 1500a998fe2b
"""

from typing import Sequence, Union

from alembic import op


revision: str = "4e76afd54850"
down_revision: Union[str, Sequence[str], None] = "1500a998fe2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Dedicated NOLOGIN capability role.
    # The actual service login is provisioned separately.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_catalog.pg_roles
                WHERE rolname = 'eka_platform_recovery'
            ) THEN
                CREATE ROLE eka_platform_recovery
                    NOLOGIN
                    NOSUPERUSER
                    NOCREATEDB
                    NOCREATEROLE
                    NOREPLICATION
                    NOBYPASSRLS;
            END IF;

            -- Enforce the expected security attributes even if
            -- the role already existed before this migration.
            ALTER ROLE eka_platform_recovery
                NOLOGIN
                NOSUPERUSER
                NOCREATEDB
                NOCREATEROLE
                NOREPLICATION
                NOBYPASSRLS;
        END;
        $$;
    """)

    # Ensure the normal runtime cannot inherit the recovery capability.
    op.execute("""
        REVOKE eka_platform_recovery FROM eka_runtime;
    """)

    # The SECURITY DEFINER function owner needs narrowly scoped access.
    # eka_rls_helper is a NOLOGIN BYPASSRLS role used only as function owner.
    op.execute("""
        GRANT SELECT ON TABLE
            public.users,
            public.authentication_identities,
            public.organizations,
            public.organization_memberships,
            public.platform_memberships
        TO eka_rls_helper;

        GRANT UPDATE (
            role,
            is_active,
            has_held_privileged_role,
            has_held_owner_role,
            updated_at
        )
        ON TABLE public.organization_memberships
        TO eka_rls_helper;

        GRANT INSERT
        ON TABLE public.organization_owner_recovery_events
        TO eka_rls_helper;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION
        app_private.recover_organization_owner(
            p_organization_id uuid,
            p_membership_id uuid
        )
        RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        DECLARE
            v_actor_user_id uuid;
            v_actor_issuer text;
            v_actor_subject text;
            v_target_user_id uuid;
            v_organization_deleted_at timestamptz;
            v_target_user_active boolean;
            v_event_id uuid;
        BEGIN
            -- Only a login explicitly granted the recovery capability
            -- may invoke this operation.
            IF NOT pg_catalog.pg_has_role(
                session_user,
                'eka_platform_recovery',
                'member'
            ) THEN
                RAISE EXCEPTION 'Recovery capability required'
                    USING ERRCODE = '42501';
            END IF;

            -- The backend must set these transaction-locally only after
            -- validating the Auth0 JWT and resolving the internal identity.
            v_actor_user_id :=
                NULLIF(
                    pg_catalog.current_setting('app.user_id', true),
                    ''
                )::uuid;

            v_actor_issuer :=
                NULLIF(
                    pg_catalog.current_setting('app.auth_issuer', true),
                    ''
                );

            v_actor_subject :=
                NULLIF(
                    pg_catalog.current_setting('app.auth_subject', true),
                    ''
                );

            IF v_actor_user_id IS NULL
               OR v_actor_issuer IS NULL
               OR v_actor_subject IS NULL THEN
                RAISE EXCEPTION 'Authenticated actor context is required'
                    USING ERRCODE = '42501';
            END IF;

            -- Confirm that the supplied OIDC identity belongs to the actor
            -- and is still active.
            IF NOT EXISTS (
                SELECT 1
                FROM public.authentication_identities AS ai
                WHERE ai.user_id = v_actor_user_id
                  AND ai.issuer = v_actor_issuer
                  AND ai.subject = v_actor_subject
                  AND ai.is_active IS TRUE
            ) THEN
                RAISE EXCEPTION 'Active actor identity not found'
                    USING ERRCODE = '42501';
            END IF;

            -- Confirm active global Platform Admin authorization.
            IF NOT EXISTS (
                SELECT 1
                FROM public.platform_memberships AS pm
                JOIN public.users AS u
                  ON u.id = pm.user_id
                WHERE pm.user_id = v_actor_user_id
                  AND pm.role = 'platform_admin'
                  AND pm.is_active IS TRUE
                  AND u.is_active IS TRUE
            ) THEN
                RAISE EXCEPTION 'Active Platform Admin authorization required'
                    USING ERRCODE = '42501';
            END IF;

            -- Synchronize with normal membership operations.
            PERFORM pg_catalog.pg_advisory_xact_lock(
                pg_catalog.hashtextextended(
                    CAST(p_organization_id AS text),
                    0
                )
            );

            -- Lock the organization row as an additional safeguard.
            SELECT o.deleted_at
              INTO v_organization_deleted_at
              FROM public.organizations AS o
             WHERE o.id = p_organization_id
             FOR UPDATE;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'Organization not found'
                    USING ERRCODE = 'P0002';
            END IF;

            IF v_organization_deleted_at IS NOT NULL THEN
                RAISE EXCEPTION 'Deleted organization cannot be recovered'
                    USING ERRCODE = '23514';
            END IF;

            -- Never restore an Owner if another active Owner exists.
            IF EXISTS (
                SELECT 1
                FROM public.organization_memberships AS om
                WHERE om.organization_id = p_organization_id
                  AND om.role = 'owner'
                  AND om.is_active IS TRUE
            ) THEN
                RAISE EXCEPTION 'Organization already has an active Owner'
                    USING ERRCODE = '23514';
            END IF;

            -- Lock and validate the exact historical membership.
            SELECT om.user_id
              INTO v_target_user_id
              FROM public.organization_memberships AS om
             WHERE om.id = p_membership_id
               AND om.organization_id = p_organization_id
               AND om.has_held_owner_role IS TRUE
             FOR UPDATE;

            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'Eligible historical Owner membership not found'
                    USING ERRCODE = 'P0002';
            END IF;

            SELECT u.is_active
              INTO v_target_user_active
              FROM public.users AS u
             WHERE u.id = v_target_user_id
             FOR UPDATE;

            IF NOT FOUND OR v_target_user_active IS NOT TRUE THEN
                RAISE EXCEPTION 'Target user is not active'
                    USING ERRCODE = '23514';
            END IF;

            -- Restore the existing membership. Do not create a new one.
            UPDATE public.organization_memberships
               SET role = 'owner',
                   is_active = TRUE,
                   has_held_privileged_role = TRUE,
                   has_held_owner_role = TRUE,
                   updated_at = pg_catalog.clock_timestamp()
             WHERE id = p_membership_id
               AND organization_id = p_organization_id
               AND user_id = v_target_user_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'Membership restoration failed'
                    USING ERRCODE = '40001';
            END IF;

            -- The audit event and membership update share this transaction.
            INSERT INTO public.organization_owner_recovery_events (
                organization_id,
                membership_id,
                recovered_user_id,
                actor_user_id,
                actor_auth_issuer,
                actor_auth_subject,
                event_type
            )
            VALUES (
                p_organization_id,
                p_membership_id,
                v_target_user_id,
                v_actor_user_id,
                v_actor_issuer,
                v_actor_subject,
                'owner_recovered'
            )
            RETURNING id INTO v_event_id;

            RETURN v_event_id;
        END;
        $function$;
    """)

    op.execute("""
        ALTER FUNCTION app_private.recover_organization_owner(uuid, uuid)
            OWNER TO eka_rls_helper;

        REVOKE ALL
        ON FUNCTION app_private.recover_organization_owner(uuid, uuid)
        FROM PUBLIC, eka_runtime;

        GRANT USAGE ON SCHEMA app_private
        TO eka_platform_recovery;

        GRANT EXECUTE
        ON FUNCTION app_private.recover_organization_owner(uuid, uuid)
        TO eka_platform_recovery;
    """)

    # Integration runtime must never receive the recovery capability.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_catalog.pg_roles
                WHERE rolname = 'eka_test_runtime'
            ) THEN
                EXECUTE
                    'REVOKE eka_platform_recovery FROM eka_test_runtime';

                EXECUTE
                    'REVOKE EXECUTE ON FUNCTION '
                    'app_private.recover_organization_owner(uuid, uuid) '
                    'FROM eka_test_runtime';
            END IF;
        END;
        $$;
    """)


def downgrade() -> None:
    op.execute("""
        REVOKE EXECUTE
        ON FUNCTION app_private.recover_organization_owner(uuid, uuid)
        FROM PUBLIC, eka_runtime, eka_platform_recovery;

        REVOKE USAGE ON SCHEMA app_private
        FROM eka_platform_recovery;

        DROP FUNCTION
        app_private.recover_organization_owner(uuid, uuid);

        REVOKE UPDATE (
            role,
            is_active,
            has_held_privileged_role,
            has_held_owner_role,
            updated_at
        )
        ON TABLE public.organization_memberships
        FROM eka_rls_helper;
    """)

    op.execute("""
        REVOKE SELECT
        ON TABLE public.users, public.authentication_identities
        FROM eka_rls_helper;
    """)

    # The capability role is deliberately retained: an external service
    # login may depend on it. It has no function access after downgrade.
