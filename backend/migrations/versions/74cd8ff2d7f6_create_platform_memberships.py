"""Create global platform memberships.

Revision ID: 74cd8ff2d7f6
Revises: 357550fa1076
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "74cd8ff2d7f6"
down_revision: Union[str, Sequence[str], None] = "357550fa1076"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Global platform-level authorization.
    # This table is intentionally outside tenant RLS.
    op.create_table(
        "platform_memberships",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'platform_admin'"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_platform_memberships",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_platform_memberships_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "user_id",
            "role",
            name="uq_platform_membership_user_role",
        ),
        sa.CheckConstraint(
            "role = 'platform_admin'",
            name="ck_platform_membership_role",
        ),
    )

    # Runtime can verify platform authorization but cannot grant it.
    # The helper role needs read access for controlled SECURITY DEFINER
    # authorization functions introduced in a later migration.
    op.execute("""
        REVOKE ALL PRIVILEGES
        ON TABLE public.platform_memberships
        FROM PUBLIC;

        GRANT SELECT
        ON TABLE public.platform_memberships
        TO eka_runtime;

        GRANT SELECT
        ON TABLE public.platform_memberships
        TO eka_rls_helper;

        REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
        ON TABLE public.platform_memberships
        FROM eka_runtime, eka_rls_helper;
    """)

    # The integration runtime is optional in non-test environments.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_catalog.pg_roles
                WHERE rolname = 'eka_test_runtime'
            ) THEN
                EXECUTE
                    'GRANT SELECT ON TABLE public.platform_memberships '
                    'TO eka_test_runtime';

                EXECUTE
                    'REVOKE INSERT, UPDATE, DELETE, TRUNCATE, '
                    'REFERENCES, TRIGGER '
                    'ON TABLE public.platform_memberships '
                    'FROM eka_test_runtime';
            END IF;
        END;
        $$;
    """)


def downgrade() -> None:
    op.execute("""
        REVOKE ALL PRIVILEGES
        ON TABLE public.platform_memberships
        FROM PUBLIC;

        REVOKE ALL PRIVILEGES
        ON TABLE public.platform_memberships
        FROM eka_runtime, eka_rls_helper;

        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_catalog.pg_roles
                WHERE rolname = 'eka_test_runtime'
            ) THEN
                EXECUTE
                    'REVOKE ALL PRIVILEGES '
                    'ON TABLE public.platform_memberships '
                    'FROM eka_test_runtime';
            END IF;
        END;
        $$;
    """)

    op.drop_table("platform_memberships")
