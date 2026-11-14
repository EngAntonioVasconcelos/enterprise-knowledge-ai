"""Accounts are created only by verified login.

Revision ID: d9a3f6b2e8c5
Revises: c4e7a1d9f3b6
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d9a3f6b2e8c5"
down_revision: Union[str, Sequence[str], None] = "c4e7a1d9f3b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Owners and admins could create an account while adding someone to
    # their organization. Invitations replace that path, so accounts are now
    # created only by app_private.provision_user, on a verified login.
    op.execute("""
        DROP POLICY users_insert_policy ON public.users;

        REVOKE INSERT ON public.users FROM eka_runtime;
    """)


def downgrade() -> None:
    op.execute("""
        GRANT INSERT ON public.users TO eka_runtime;

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
