"""Create organization invitations.

Revision ID: c4e7a1d9f3b6
Revises: b7d2e5a8c1f4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4e7a1d9f3b6"
down_revision: Union[str, Sequence[str], None] = "b7d2e5a8c1f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "expires_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "accepted_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("accepted_by_user_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_organization_invitations"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_invitations_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_invitations_invited_by_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_invitations_accepted_by_user_id_users",
        ),
        sa.UniqueConstraint("token_hash", name="uq_invitation_token_hash"),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'member', 'viewer')",
            name="ck_invitation_role",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_invitation_status",
        ),
        sa.CheckConstraint(
            "email = lower(email)",
            name="ck_invitation_email_lowercase",
        ),
    )

    op.create_index(
        "ix_organization_invitations_organization_id",
        "organization_invitations",
        ["organization_id"],
    )

    # One pending invitation per person and organization.
    op.create_index(
        "uq_invitation_pending_email",
        "organization_invitations",
        ["organization_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    # Owners and admins manage the invitations of their organization.
    # Nobody else reads them: an invitee accepts through
    # app_private.accept_invitation, which only reveals the invitation that
    # matches the token they hold.
    op.execute("""
        REVOKE ALL ON public.organization_invitations FROM PUBLIC;

        GRANT SELECT, INSERT, UPDATE
        ON public.organization_invitations
        TO eka_runtime;

        GRANT SELECT, UPDATE
        ON public.organization_invitations
        TO eka_rls_helper;

        GRANT INSERT ON public.organization_memberships TO eka_rls_helper;

        ALTER TABLE public.organization_invitations
            ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.organization_invitations
            FORCE ROW LEVEL SECURITY;

        CREATE POLICY organization_invitations_select_policy
        ON public.organization_invitations
        FOR SELECT
        TO PUBLIC
        USING (app_private.can_manage_organization(organization_id));

        CREATE POLICY organization_invitations_insert_policy
        ON public.organization_invitations
        FOR INSERT
        TO PUBLIC
        WITH CHECK (
            app_private.can_manage_organization(organization_id)
            AND status = 'pending'
            AND invited_by_user_id =
                NULLIF(current_setting('app.user_id', true), '')::uuid
        );

        CREATE POLICY organization_invitations_update_policy
        ON public.organization_invitations
        FOR UPDATE
        TO PUBLIC
        USING (app_private.can_manage_organization(organization_id))
        WITH CHECK (
            app_private.can_manage_organization(organization_id)
            AND status IN ('revoked', 'expired')
        );
    """)

    # Accepting is the only way an invitee joins: the token must match a
    # pending, unexpired invitation addressed to the caller's e-mail.
    op.execute("""
        CREATE FUNCTION app_private.accept_invitation(p_token text)
        RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        DECLARE
            v_user_id uuid :=
                NULLIF(current_setting('app.user_id', true), '')::uuid;
            v_hash text;
            v_invitation public.organization_invitations%ROWTYPE;
            v_email text;
            v_membership public.organization_memberships%ROWTYPE;
            v_membership_id uuid;
        BEGIN
            IF NOT app_private.has_authenticated_context() THEN
                RAISE EXCEPTION
                    'an authenticated user is required'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            v_hash := encode(
                sha256(convert_to(coalesce(p_token, ''), 'UTF8')),
                'hex'
            );

            SELECT * INTO v_invitation
            FROM public.organization_invitations
            WHERE token_hash = v_hash
            FOR UPDATE;

            IF NOT FOUND OR v_invitation.status <> 'pending' THEN
                RAISE EXCEPTION
                    'invitation not found or no longer valid'
                    USING ERRCODE = 'no_data_found';
            END IF;

            IF v_invitation.expires_at <= now() THEN
                RAISE EXCEPTION
                    'invitation not found or no longer valid'
                    USING ERRCODE = 'no_data_found';
            END IF;

            SELECT u.email INTO v_email
            FROM public.users AS u
            WHERE u.id = v_user_id
              AND u.is_active;

            IF v_email IS DISTINCT FROM v_invitation.email THEN
                RAISE EXCEPTION
                    'invitation was sent to another email address'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            -- Same key as membership changes and owner recovery.
            PERFORM pg_advisory_xact_lock(
                hashtextextended(v_invitation.organization_id::text, 0)
            );

            SELECT * INTO v_membership
            FROM public.organization_memberships
            WHERE organization_id = v_invitation.organization_id
              AND user_id = v_user_id;

            IF FOUND THEN
                IF v_membership.is_active THEN
                    RAISE EXCEPTION
                        'already a member of the organization'
                        USING ERRCODE = 'unique_violation';
                END IF;

                UPDATE public.organization_memberships
                SET role = v_invitation.role,
                    is_active = true,
                    has_held_privileged_role =
                        has_held_privileged_role
                        OR v_invitation.role IN ('owner', 'admin'),
                    has_held_owner_role =
                        has_held_owner_role OR v_invitation.role = 'owner',
                    updated_at = clock_timestamp()
                WHERE id = v_membership.id;

                v_membership_id := v_membership.id;
            ELSE
                v_membership_id := gen_random_uuid();

                INSERT INTO public.organization_memberships (
                    id, organization_id, user_id, role, is_active,
                    has_held_privileged_role, has_held_owner_role,
                    created_at, updated_at
                )
                VALUES (
                    v_membership_id,
                    v_invitation.organization_id,
                    v_user_id,
                    v_invitation.role,
                    true,
                    v_invitation.role IN ('owner', 'admin'),
                    v_invitation.role = 'owner',
                    clock_timestamp(),
                    clock_timestamp()
                );
            END IF;

            UPDATE public.organization_invitations
            SET status = 'accepted',
                accepted_at = clock_timestamp(),
                accepted_by_user_id = v_user_id
            WHERE id = v_invitation.id;

            RETURN v_membership_id;
        END;
        $function$;

        ALTER FUNCTION app_private.accept_invitation(text)
            OWNER TO eka_rls_helper;

        REVOKE ALL ON FUNCTION app_private.accept_invitation(text)
            FROM PUBLIC;

        GRANT EXECUTE ON FUNCTION app_private.accept_invitation(text)
            TO eka_runtime;
    """)


def downgrade() -> None:
    op.execute("""
        DROP FUNCTION app_private.accept_invitation(text);

        REVOKE INSERT ON public.organization_memberships
            FROM eka_rls_helper;
    """)

    op.drop_index(
        "uq_invitation_pending_email",
        table_name="organization_invitations",
    )
    op.drop_index(
        "ix_organization_invitations_organization_id",
        table_name="organization_invitations",
    )
    op.drop_table("organization_invitations")
