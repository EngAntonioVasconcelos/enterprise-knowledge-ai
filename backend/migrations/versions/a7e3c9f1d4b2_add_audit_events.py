"""Add the audit log, written by triggers.

Revision ID: a7e3c9f1d4b2
Revises: f5c1a8d3e6b9
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a7e3c9f1d4b2"
down_revision: Union[str, Sequence[str], None] = "f5c1a8d3e6b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "actor_database_login", sa.String(length=255), nullable=False
        ),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
            name="fk_audit_events_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_audit_events_actor_user_id_users",
        ),
    )
    op.create_index(
        "ix_audit_events_organization_created",
        "audit_events",
        ["organization_id", "created_at"],
    )

    # Owners and admins read the log of their organization. Nobody writes to
    # it but the triggers below, and nobody changes or removes a row.
    op.execute("""
        REVOKE ALL ON public.audit_events FROM PUBLIC;

        GRANT SELECT ON public.audit_events TO eka_runtime;
        GRANT INSERT ON public.audit_events TO eka_rls_helper;

        ALTER TABLE public.audit_events ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.audit_events FORCE ROW LEVEL SECURITY;

        CREATE POLICY audit_events_select_policy
        ON public.audit_events
        FOR SELECT
        TO PUBLIC
        USING (app_private.can_manage_organization(organization_id));
    """)

    op.execute("""
        CREATE FUNCTION app_private.record_audit_event(
            p_organization_id uuid,
            p_action text,
            p_target_type text,
            p_target_id uuid,
            p_details jsonb
        )
        RETURNS void
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
            INSERT INTO public.audit_events (
                organization_id, actor_user_id, actor_database_login,
                action, target_type, target_id, details, created_at
            )
            VALUES (
                p_organization_id,
                NULLIF(current_setting('app.user_id', true), '')::uuid,
                session_user,
                p_action,
                p_target_type,
                p_target_id,
                p_details,
                clock_timestamp()
            );
        $function$;

        ALTER FUNCTION
            app_private.record_audit_event(uuid, text, text, uuid, jsonb)
            OWNER TO eka_rls_helper;
        REVOKE ALL ON FUNCTION
            app_private.record_audit_event(uuid, text, text, uuid, jsonb)
            FROM PUBLIC;
    """)

    op.execute("""
        CREATE FUNCTION app_private.audit_membership_change()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                PERFORM app_private.record_audit_event(
                    NEW.organization_id, 'membership.created', 'membership',
                    NEW.id,
                    jsonb_build_object('user_id', NEW.user_id, 'role', NEW.role)
                );
                RETURN NEW;
            END IF;

            IF NEW.role IS DISTINCT FROM OLD.role THEN
                PERFORM app_private.record_audit_event(
                    NEW.organization_id, 'membership.role_changed',
                    'membership', NEW.id,
                    jsonb_build_object(
                        'user_id', NEW.user_id,
                        'from', OLD.role,
                        'to', NEW.role
                    )
                );
            END IF;

            IF NEW.is_active IS DISTINCT FROM OLD.is_active THEN
                PERFORM app_private.record_audit_event(
                    NEW.organization_id,
                    CASE WHEN NEW.is_active
                         THEN 'membership.reactivated'
                         ELSE 'membership.deactivated'
                    END,
                    'membership', NEW.id,
                    jsonb_build_object('user_id', NEW.user_id, 'role', NEW.role)
                );
            END IF;

            RETURN NEW;
        END;
        $function$;

        CREATE FUNCTION app_private.audit_invitation_change()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                PERFORM app_private.record_audit_event(
                    NEW.organization_id, 'invitation.created', 'invitation',
                    NEW.id,
                    jsonb_build_object('email', NEW.email, 'role', NEW.role)
                );
            ELSIF NEW.status IS DISTINCT FROM OLD.status THEN
                PERFORM app_private.record_audit_event(
                    NEW.organization_id, 'invitation.' || NEW.status,
                    'invitation', NEW.id,
                    jsonb_build_object('email', NEW.email, 'role', NEW.role)
                );
            END IF;

            RETURN NEW;
        END;
        $function$;

        CREATE FUNCTION app_private.audit_organization_change()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                PERFORM app_private.record_audit_event(
                    NEW.id, 'organization.created', 'organization', NEW.id,
                    jsonb_build_object('name', NEW.name, 'slug', NEW.slug)
                );
                RETURN NEW;
            END IF;

            IF NEW.name IS DISTINCT FROM OLD.name
               OR NEW.slug IS DISTINCT FROM OLD.slug
            THEN
                PERFORM app_private.record_audit_event(
                    NEW.id, 'organization.updated', 'organization', NEW.id,
                    jsonb_build_object(
                        'name', jsonb_build_array(OLD.name, NEW.name),
                        'slug', jsonb_build_array(OLD.slug, NEW.slug)
                    )
                );
            END IF;

            IF NEW.status IS DISTINCT FROM OLD.status THEN
                PERFORM app_private.record_audit_event(
                    NEW.id, 'organization.status_changed', 'organization',
                    NEW.id,
                    jsonb_build_object('from', OLD.status, 'to', NEW.status)
                );
            END IF;

            RETURN NEW;
        END;
        $function$;

        ALTER FUNCTION app_private.audit_membership_change()
            OWNER TO eka_rls_helper;
        ALTER FUNCTION app_private.audit_invitation_change()
            OWNER TO eka_rls_helper;
        ALTER FUNCTION app_private.audit_organization_change()
            OWNER TO eka_rls_helper;

        REVOKE ALL ON FUNCTION app_private.audit_membership_change()
            FROM PUBLIC;
        REVOKE ALL ON FUNCTION app_private.audit_invitation_change()
            FROM PUBLIC;
        REVOKE ALL ON FUNCTION app_private.audit_organization_change()
            FROM PUBLIC;

        CREATE TRIGGER trg_audit_membership_change
        AFTER INSERT OR UPDATE ON public.organization_memberships
        FOR EACH ROW
        EXECUTE FUNCTION app_private.audit_membership_change();

        CREATE TRIGGER trg_audit_invitation_change
        AFTER INSERT OR UPDATE ON public.organization_invitations
        FOR EACH ROW
        EXECUTE FUNCTION app_private.audit_invitation_change();

        CREATE TRIGGER trg_audit_organization_change
        AFTER INSERT OR UPDATE ON public.organizations
        FOR EACH ROW
        EXECUTE FUNCTION app_private.audit_organization_change();
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER trg_audit_organization_change ON public.organizations;
        DROP TRIGGER trg_audit_invitation_change
            ON public.organization_invitations;
        DROP TRIGGER trg_audit_membership_change
            ON public.organization_memberships;

        DROP FUNCTION app_private.audit_organization_change();
        DROP FUNCTION app_private.audit_invitation_change();
        DROP FUNCTION app_private.audit_membership_change();
        DROP FUNCTION
            app_private.record_audit_event(uuid, text, text, uuid, jsonb);
    """)

    op.drop_index(
        "ix_audit_events_organization_created", table_name="audit_events"
    )
    op.drop_table("audit_events")
