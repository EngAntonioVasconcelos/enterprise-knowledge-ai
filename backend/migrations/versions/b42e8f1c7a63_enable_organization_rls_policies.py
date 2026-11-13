"""enable_organization_rls_policies

Revision ID: b42e8f1c7a63
Revises: 9a71c4d2e6b8
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b42e8f1c7a63"
down_revision: Union[str, Sequence[str], None] = "9a71c4d2e6b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Organizations: enable and force row-level security.
    op.execute("""
        ALTER TABLE public.organizations
            ENABLE ROW LEVEL SECURITY;

        ALTER TABLE public.organizations
            FORCE ROW LEVEL SECURITY;
    """)

    # An active member can read their organization.
    # The creator can also read it during the initial owner bootstrap.
    op.execute("""
        CREATE POLICY organizations_select_policy
        ON public.organizations
        FOR SELECT
        TO PUBLIC
        USING (
            app_private.has_active_membership(id)
            OR app_private.is_bootstrap_creator(id)
        );
    """)

    # A new organization must record the authenticated creator.
    op.execute("""
        CREATE POLICY organizations_insert_policy
        ON public.organizations
        FOR INSERT
        TO PUBLIC
        WITH CHECK (
            app_private.has_authenticated_context()
            AND created_by_user_id =
                NULLIF(
                    current_setting('app.user_id', true), ''
                )::uuid
        );
    """)

    # Only active owners and admins can update their organization.
    op.execute("""
        CREATE POLICY organizations_update_policy
        ON public.organizations
        FOR UPDATE
        TO PUBLIC
        USING (
            app_private.can_manage_organization(id)
        )
        WITH CHECK (
            app_private.can_manage_organization(id)
        );
    """)

    # Organization memberships: enable and force row-level security.
    op.execute("""
        ALTER TABLE public.organization_memberships
            ENABLE ROW LEVEL SECURITY;

        ALTER TABLE public.organization_memberships
            FORCE ROW LEVEL SECURITY;
    """)

    # Members can read their own membership.
    # Organization managers can read memberships within their organization.
    op.execute("""
        CREATE POLICY organization_memberships_select_policy
        ON public.organization_memberships
        FOR SELECT
        TO PUBLIC
        USING (
            (
                app_private.has_authenticated_context()
                AND user_id =
                    NULLIF(
                        current_setting('app.user_id', true), ''
                    )::uuid
            )
            OR app_private.can_manage_organization(organization_id)
        );
    """)

    # Managers can add memberships.
    # The bootstrap exception permits only the creator to insert
    # their own first active owner membership.
    op.execute("""
        CREATE POLICY organization_memberships_insert_policy
        ON public.organization_memberships
        FOR INSERT
        TO PUBLIC
        WITH CHECK (
            app_private.can_manage_organization(organization_id)
            OR (
                app_private.is_bootstrap_creator(organization_id)
                AND role = 'owner'
                AND user_id =
                    NULLIF(
                        current_setting('app.user_id', true), ''
                    )::uuid
                AND is_active IS TRUE
                AND has_held_privileged_role IS TRUE
            )
        );
    """)

    # Only active owners and admins can update memberships
    # within organizations they manage.
    op.execute("""
        CREATE POLICY organization_memberships_update_policy
        ON public.organization_memberships
        FOR UPDATE
        TO PUBLIC
        USING (
            app_private.can_manage_organization(organization_id)
        )
        WITH CHECK (
            app_private.can_manage_organization(organization_id)
        );
    """)


def downgrade() -> None:
    # Remove membership policies first.
    op.execute("""
        DROP POLICY IF EXISTS organization_memberships_update_policy
            ON public.organization_memberships;

        DROP POLICY IF EXISTS organization_memberships_insert_policy
            ON public.organization_memberships;

        DROP POLICY IF EXISTS organization_memberships_select_policy
            ON public.organization_memberships;
    """)

    # Remove organization policies.
    op.execute("""
        DROP POLICY IF EXISTS organizations_update_policy
            ON public.organizations;

        DROP POLICY IF EXISTS organizations_insert_policy
            ON public.organizations;

        DROP POLICY IF EXISTS organizations_select_policy
            ON public.organizations;
    """)

    # Restore the previous RLS state.
    op.execute("""
        ALTER TABLE public.organization_memberships
            NO FORCE ROW LEVEL SECURITY;

        ALTER TABLE public.organization_memberships
            DISABLE ROW LEVEL SECURITY;

        ALTER TABLE public.organizations
            NO FORCE ROW LEVEL SECURITY;

        ALTER TABLE public.organizations
            DISABLE ROW LEVEL SECURITY;
    """)
