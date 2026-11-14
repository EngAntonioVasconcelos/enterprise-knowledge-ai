"""Redesign organization owner recovery.

Revision ID: b7d2e5a8c1f4
Revises: f1a4c7e93b28
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b7d2e5a8c1f4"
down_revision: Union[str, Sequence[str], None] = "f1a4c7e93b28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The previous function, restored by downgrade. It never worked: it locked
# rows its owner could not update, and it only acted when an organization
# had no active owner, which the membership triggers make impossible.
PREVIOUS_FUNCTION = """
        CREATE FUNCTION
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
"""


def upgrade() -> None:
    op.execute("""
        DROP FUNCTION app_private.recover_organization_owner(uuid, uuid);
    """)

    # Recovery is an operational command, run by a platform operator through
    # a database login that holds eka_platform_recovery. There is no OIDC
    # token in that path, so the actor is recorded by user id and login.
    # The table never received a row: the previous function always failed.
    op.execute("""
        ALTER TABLE public.organization_owner_recovery_events
            ALTER COLUMN actor_auth_issuer DROP NOT NULL,
            ALTER COLUMN actor_auth_subject DROP NOT NULL,
            ADD COLUMN reason text NOT NULL,
            ADD COLUMN database_login varchar(255) NOT NULL,
            ADD CONSTRAINT ck_owner_recovery_event_reason
                CHECK (length(btrim(reason)) >= 10);
    """)

    # Promotes an active member to owner and deactivates every other active
    # owner, in one transaction with its audit event. Promotion happens
    # first, so the last-owner trigger always sees an active owner.
    op.execute("""
        CREATE FUNCTION app_private.recover_organization_owner(
            p_organization_id uuid,
            p_membership_id uuid,
            p_actor_user_id uuid,
            p_reason text
        )
        RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        DECLARE
            v_reason text := btrim(coalesce(p_reason, ''));
            v_target_user_id uuid;
            v_target_role text;
            v_event_id uuid;
        BEGIN
            IF NOT pg_has_role(
                session_user, 'eka_platform_recovery', 'member'
            ) THEN
                RAISE EXCEPTION
                    'owner recovery requires the platform recovery role'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            IF length(v_reason) < 10 THEN
                RAISE EXCEPTION
                    'owner recovery requires a reason of at least 10 characters'
                    USING ERRCODE = 'invalid_parameter_value';
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM public.platform_memberships AS pm
                JOIN public.users AS u ON u.id = pm.user_id
                WHERE pm.user_id = p_actor_user_id
                  AND pm.role = 'platform_admin'
                  AND pm.is_active
                  AND u.is_active
            ) THEN
                RAISE EXCEPTION
                    'owner recovery requires an active platform admin'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            -- Same key as the last-owner trigger and the bootstrap path.
            PERFORM pg_advisory_xact_lock(
                hashtextextended(p_organization_id::text, 0)
            );

            IF NOT EXISTS (
                SELECT 1
                FROM public.organizations AS o
                WHERE o.id = p_organization_id
                  AND o.deleted_at IS NULL
            ) THEN
                RAISE EXCEPTION
                    'organization not found or deleted'
                    USING ERRCODE = 'no_data_found';
            END IF;

            SELECT m.user_id, m.role
            INTO v_target_user_id, v_target_role
            FROM public.organization_memberships AS m
            JOIN public.users AS u ON u.id = m.user_id
            WHERE m.id = p_membership_id
              AND m.organization_id = p_organization_id
              AND m.is_active
              AND u.is_active;

            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'the new owner must be an active member of the organization'
                    USING ERRCODE = 'no_data_found';
            END IF;

            IF v_target_role = 'owner' THEN
                RAISE EXCEPTION
                    'the member is already an owner'
                    USING ERRCODE = 'invalid_parameter_value';
            END IF;

            UPDATE public.organization_memberships
            SET role = 'owner',
                has_held_privileged_role = true,
                has_held_owner_role = true,
                updated_at = clock_timestamp()
            WHERE id = p_membership_id;

            UPDATE public.organization_memberships
            SET is_active = false,
                updated_at = clock_timestamp()
            WHERE organization_id = p_organization_id
              AND id <> p_membership_id
              AND role = 'owner'
              AND is_active;

            -- The id is generated here: RETURNING would need SELECT on the
            -- audit table, which this function's owner does not hold.
            v_event_id := gen_random_uuid();

            INSERT INTO public.organization_owner_recovery_events (
                id,
                organization_id,
                membership_id,
                recovered_user_id,
                actor_user_id,
                event_type,
                reason,
                database_login
            )
            VALUES (
                v_event_id,
                p_organization_id,
                p_membership_id,
                v_target_user_id,
                p_actor_user_id,
                'owner_recovered',
                v_reason,
                session_user
            );

            RETURN v_event_id;
        END;
        $function$;

        ALTER FUNCTION
            app_private.recover_organization_owner(uuid, uuid, uuid, text)
            OWNER TO eka_rls_helper;

        REVOKE ALL ON FUNCTION
            app_private.recover_organization_owner(uuid, uuid, uuid, text)
            FROM PUBLIC, eka_runtime;

        GRANT EXECUTE ON FUNCTION
            app_private.recover_organization_owner(uuid, uuid, uuid, text)
            TO eka_platform_recovery;
    """)


def downgrade() -> None:
    op.execute("""
        DROP FUNCTION
            app_private.recover_organization_owner(uuid, uuid, uuid, text);

        ALTER TABLE public.organization_owner_recovery_events
            DROP CONSTRAINT ck_owner_recovery_event_reason,
            DROP COLUMN database_login,
            DROP COLUMN reason,
            ALTER COLUMN actor_auth_subject SET NOT NULL,
            ALTER COLUMN actor_auth_issuer SET NOT NULL;
    """)

    op.execute(PREVIOUS_FUNCTION)

    op.execute("""
        ALTER FUNCTION app_private.recover_organization_owner(uuid, uuid)
            OWNER TO eka_rls_helper;

        REVOKE ALL
        ON FUNCTION app_private.recover_organization_owner(uuid, uuid)
        FROM PUBLIC, eka_runtime;

        GRANT EXECUTE
        ON FUNCTION app_private.recover_organization_owner(uuid, uuid)
        TO eka_platform_recovery;
    """)
