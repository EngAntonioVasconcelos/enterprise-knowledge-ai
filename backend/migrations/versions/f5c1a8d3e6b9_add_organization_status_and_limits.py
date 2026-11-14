"""Add organization status and the per-user creation limit.

Revision ID: f5c1a8d3e6b9
Revises: e2b8c4f7a9d1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f5c1a8d3e6b9"
down_revision: Union[str, Sequence[str], None] = "e2b8c4f7a9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PREVIOUS_ORGANIZATION_INVARIANTS = """
    CREATE OR REPLACE FUNCTION app_private.protect_organization_invariants()
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
"""


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_organization_status",
        "organizations",
        "status IN ('active', 'suspended', 'pending_deletion', 'deleted')",
    )

    # Platform limits live in the database, outside the application's
    # reach: an operator changes them with one UPDATE, no migration needed.
    op.execute("""
        CREATE TABLE app_private.platform_limits (
            id boolean PRIMARY KEY DEFAULT true CHECK (id),
            max_organizations_per_user integer NOT NULL
                CHECK (max_organizations_per_user > 0)
        );

        INSERT INTO app_private.platform_limits (max_organizations_per_user)
        VALUES (3);

        ALTER TABLE app_private.platform_limits OWNER TO eka_rls_helper;
        REVOKE ALL ON app_private.platform_limits FROM PUBLIC;
    """)

    # A new organization starts active, and nobody creates more than the
    # limit. Counting runs as the helper role, so organizations the creator
    # can no longer see still count.
    op.execute("""
        CREATE FUNCTION app_private.enforce_organization_creation()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $$
        DECLARE
            v_limit integer;
            v_created integer;
        BEGIN
            IF NEW.status <> 'active' THEN
                RAISE EXCEPTION
                    'a new organization must be active'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;

            IF NEW.created_by_user_id IS NULL THEN
                RETURN NEW;
            END IF;

            -- Serialize concurrent creations by the same person.
            PERFORM pg_advisory_xact_lock(
                hashtextextended(
                    'create-organization:' || NEW.created_by_user_id::text,
                    0
                )
            );

            SELECT max_organizations_per_user INTO v_limit
            FROM app_private.platform_limits;

            SELECT count(*) INTO v_created
            FROM public.organizations AS o
            WHERE o.created_by_user_id = NEW.created_by_user_id
              AND o.status <> 'deleted';

            IF v_created >= v_limit THEN
                RAISE EXCEPTION
                    'organization limit reached'
                    USING ERRCODE = 'check_violation';
            END IF;

            RETURN NEW;
        END;
        $$;

        ALTER FUNCTION app_private.enforce_organization_creation()
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.enforce_organization_creation()
            FROM PUBLIC;

        CREATE TRIGGER trg_enforce_organization_creation
        BEFORE INSERT ON public.organizations
        FOR EACH ROW
        EXECUTE FUNCTION app_private.enforce_organization_creation();
    """)

    # Only the platform changes an organization's status or deletion date,
    # and an organization that is not active cannot be edited in the app.
    op.execute("""
        CREATE OR REPLACE FUNCTION app_private.protect_organization_invariants()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            v_platform boolean := pg_has_role(
                session_user, 'eka_platform_recovery', 'member'
            );
        BEGIN
            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.created_by_user_id
                  IS DISTINCT FROM OLD.created_by_user_id
            THEN
                RAISE EXCEPTION
                    'organization identity and creator are immutable'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;

            IF NOT v_platform THEN
                IF NEW.status IS DISTINCT FROM OLD.status
                   OR NEW.deleted_at IS DISTINCT FROM OLD.deleted_at
                THEN
                    RAISE EXCEPTION
                        'organization status can only be changed by the platform'
                        USING ERRCODE = 'insufficient_privilege';
                END IF;

                IF OLD.status <> 'active' THEN
                    RAISE EXCEPTION
                        'organization is not active'
                        USING ERRCODE = 'object_not_in_prerequisite_state';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$;
    """)

    # Memberships and invitations of an organization that is not active are
    # read-only, for the application and for the functions it calls.
    op.execute("""
        CREATE FUNCTION app_private.require_active_organization()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF pg_has_role(session_user, 'eka_platform_recovery', 'member') THEN
                RETURN NEW;
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM public.organizations AS o
                WHERE o.id = NEW.organization_id
                  AND o.status = 'active'
            ) THEN
                RAISE EXCEPTION
                    'organization is not active'
                    USING ERRCODE = 'object_not_in_prerequisite_state';
            END IF;

            RETURN NEW;
        END;
        $$;

        ALTER FUNCTION app_private.require_active_organization()
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION app_private.require_active_organization()
            FROM PUBLIC;

        CREATE TRIGGER trg_require_active_organization
        BEFORE INSERT OR UPDATE ON public.organization_memberships
        FOR EACH ROW
        EXECUTE FUNCTION app_private.require_active_organization();

        CREATE TRIGGER trg_require_active_organization
        BEFORE INSERT OR UPDATE ON public.organization_invitations
        FOR EACH ROW
        EXECUTE FUNCTION app_private.require_active_organization();
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER trg_require_active_organization
            ON public.organization_invitations;
        DROP TRIGGER trg_require_active_organization
            ON public.organization_memberships;
        DROP FUNCTION app_private.require_active_organization();

        DROP TRIGGER trg_enforce_organization_creation
            ON public.organizations;
        DROP FUNCTION app_private.enforce_organization_creation();

        DROP TABLE app_private.platform_limits;
    """)

    op.execute(PREVIOUS_ORGANIZATION_INVARIANTS)

    op.drop_constraint(
        "ck_organization_status", "organizations", type_="check"
    )
    op.drop_column("organizations", "status")
