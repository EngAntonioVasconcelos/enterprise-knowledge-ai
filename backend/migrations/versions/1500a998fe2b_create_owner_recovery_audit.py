"""Create owner recovery audit.

Revision ID: 1500a998fe2b
Revises: 74cd8ff2d7f6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1500a998fe2b"
down_revision: Union[str, Sequence[str], None] = "74cd8ff2d7f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Required target key for the composite audit foreign key.
    op.create_unique_constraint(
        "uq_membership_organization_id_id_user_id",
        "organization_memberships",
        ["organization_id", "id", "user_id"],
    )

    op.create_table(
        "organization_owner_recovery_events",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("recovered_user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "actor_auth_issuer",
            sa.String(length=512),
            nullable=False,
        ),
        sa.Column(
            "actor_auth_subject",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'owner_recovered'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_organization_owner_recovery_events",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id", "recovered_user_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.id",
                "organization_memberships.user_id",
            ],
            name="fk_owner_recovery_event_membership_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_owner_recovery_event_actor_user",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "event_type = 'owner_recovered'",
            name="ck_owner_recovery_event_type",
        ),
    )

    op.create_index(
        "ix_owner_recovery_events_organization_created",
        "organization_owner_recovery_events",
        ["organization_id", "created_at"],
        unique=False,
    )

    op.create_index(
        "ix_owner_recovery_events_actor_user",
        "organization_owner_recovery_events",
        ["actor_user_id"],
        unique=False,
    )

    op.create_index(
        "ix_owner_recovery_events_recovered_user",
        "organization_owner_recovery_events",
        ["recovered_user_id"],
        unique=False,
    )

    # Owner-only read access through the existing D-01 helper.
    op.execute("""
        REVOKE ALL PRIVILEGES
        ON TABLE public.organization_owner_recovery_events
        FROM PUBLIC;

        GRANT SELECT
        ON TABLE public.organization_owner_recovery_events
        TO eka_runtime;

        GRANT INSERT
        ON TABLE public.organization_owner_recovery_events
        TO eka_rls_helper;

        REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
        ON TABLE public.organization_owner_recovery_events
        FROM eka_runtime, eka_rls_helper;

        ALTER TABLE public.organization_owner_recovery_events
            ENABLE ROW LEVEL SECURITY;

        ALTER TABLE public.organization_owner_recovery_events
            FORCE ROW LEVEL SECURITY;

        CREATE POLICY owner_recovery_events_select_owner_policy
        ON public.organization_owner_recovery_events
        FOR SELECT
        USING (
            app_private.can_manage_organization_as_owner(
                organization_id
            )
        );
    """)

    # Integration runtime is optional outside the test environment.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_catalog.pg_roles
                WHERE rolname = 'eka_test_runtime'
            ) THEN
                EXECUTE
                    'GRANT SELECT ON TABLE '
                    'public.organization_owner_recovery_events '
                    'TO eka_test_runtime';

                EXECUTE
                    'REVOKE INSERT, UPDATE, DELETE, TRUNCATE, '
                    'REFERENCES, TRIGGER '
                    'ON TABLE public.organization_owner_recovery_events '
                    'FROM eka_test_runtime';
            END IF;
        END;
        $$;
    """)


def downgrade() -> None:
    op.execute("""
        DROP POLICY IF EXISTS
            owner_recovery_events_select_owner_policy
        ON public.organization_owner_recovery_events;

        REVOKE ALL PRIVILEGES
        ON TABLE public.organization_owner_recovery_events
        FROM PUBLIC, eka_runtime, eka_rls_helper;

        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_catalog.pg_roles
                WHERE rolname = 'eka_test_runtime'
            ) THEN
                EXECUTE
                    'REVOKE ALL PRIVILEGES ON TABLE '
                    'public.organization_owner_recovery_events '
                    'FROM eka_test_runtime';
            END IF;
        END;
        $$;
    """)

    op.drop_index(
        "ix_owner_recovery_events_recovered_user",
        table_name="organization_owner_recovery_events",
    )

    op.drop_index(
        "ix_owner_recovery_events_actor_user",
        table_name="organization_owner_recovery_events",
    )

    op.drop_index(
        "ix_owner_recovery_events_organization_created",
        table_name="organization_owner_recovery_events",
    )

    op.drop_table("organization_owner_recovery_events")

    op.drop_constraint(
        "uq_membership_organization_id_id_user_id",
        "organization_memberships",
        type_="unique",
    )
