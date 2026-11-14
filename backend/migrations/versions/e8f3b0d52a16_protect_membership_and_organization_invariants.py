"""Protect membership and organization invariants in the database.

Revision ID: e8f3b0d52a16
Revises: d7e2a9c41f05
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e8f3b0d52a16"
down_revision: Union[str, Sequence[str], None] = "d7e2a9c41f05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Row-level security decides which rows a caller may update. It cannot
    # express which columns may change, nor rules that span several rows.
    # These triggers enforce both, for every caller, whatever the policy.
    op.execute("""
        CREATE FUNCTION app_private.protect_membership_invariants()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.user_id IS DISTINCT FROM OLD.user_id
            THEN
                RAISE EXCEPTION
                    'membership identity is immutable'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;

            IF (OLD.has_held_privileged_role
                AND NOT NEW.has_held_privileged_role)
               OR (OLD.has_held_owner_role
                   AND NOT NEW.has_held_owner_role)
            THEN
                RAISE EXCEPTION
                    'membership role history cannot be erased'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;

            IF OLD.role = 'owner'
               AND OLD.is_active
               AND (NEW.role <> 'owner' OR NOT NEW.is_active)
            THEN
                -- Serialize owner removals per organization. The same key
                -- is used by the bootstrap and owner recovery paths.
                PERFORM pg_catalog.pg_advisory_xact_lock(
                    pg_catalog.hashtextextended(
                        OLD.organization_id::text,
                        0
                    )
                );

                IF NOT EXISTS (
                    SELECT 1
                    FROM public.organization_memberships AS m
                    WHERE m.organization_id = OLD.organization_id
                      AND m.id <> OLD.id
                      AND m.role = 'owner'
                      AND m.is_active
                ) THEN
                    RAISE EXCEPTION
                        'an organization must keep at least one active owner'
                        USING ERRCODE = 'integrity_constraint_violation';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$;

        ALTER FUNCTION app_private.protect_membership_invariants()
            OWNER TO eka_rls_helper;

        REVOKE ALL
        ON FUNCTION app_private.protect_membership_invariants()
        FROM PUBLIC;

        CREATE TRIGGER trg_protect_membership_invariants
        BEFORE UPDATE ON public.organization_memberships
        FOR EACH ROW
        EXECUTE FUNCTION app_private.protect_membership_invariants();
    """)

    op.execute("""
        CREATE FUNCTION app_private.protect_organization_invariants()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.created_by_user_id
                  IS DISTINCT FROM OLD.created_by_user_id
            THEN
                RAISE EXCEPTION
                    'organization identity and creator are immutable'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;

            RETURN NEW;
        END;
        $$;

        ALTER FUNCTION app_private.protect_organization_invariants()
            OWNER TO eka_rls_helper;

        REVOKE ALL
        ON FUNCTION app_private.protect_organization_invariants()
        FROM PUBLIC;

        CREATE TRIGGER trg_protect_organization_invariants
        BEFORE UPDATE ON public.organizations
        FOR EACH ROW
        EXECUTE FUNCTION app_private.protect_organization_invariants();
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER trg_protect_organization_invariants
        ON public.organizations;

        DROP FUNCTION app_private.protect_organization_invariants();

        DROP TRIGGER trg_protect_membership_invariants
        ON public.organization_memberships;

        DROP FUNCTION app_private.protect_membership_invariants();
    """)
