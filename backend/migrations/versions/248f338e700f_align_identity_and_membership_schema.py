
"""Align identity and membership schema.

Revision ID: 248f338e700f
Revises: 8eb5d7953045
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision: str = "248f338e700f"
down_revision: Union[str, Sequence[str], None] = "8eb5d7953045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""

    if not context.is_offline_mode():
        connection = op.get_bind()

        user_count = connection.execute(
            sa.text("SELECT COUNT(*) FROM users")
        ).scalar_one()

        if user_count > 0:
            raise RuntimeError(
                "Migration aborted: users table is not empty. "
                "A controlled data migration is required before "
                "changing the user identity schema."
            )

    # Keep the remaining migration operations below unchanged.
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'member', 'viewer')",
            name="ck_membership_role",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_membership_organization_user",
        ),
    )

    op.create_index(
        "ix_organization_memberships_organization_id",
        "organization_memberships",
        ["organization_id"],
        unique=False,
    )

    op.create_index(
        "ix_organization_memberships_user_id",
        "organization_memberships",
        ["user_id"],
        unique=False,
    )

    # Create authentication identities.
    op.create_table(
        "authentication_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(length=512), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "last_authenticated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "issuer",
            "subject",
            name="uq_authentication_identity_issuer_subject",
        ),
    )

    op.create_index(
        "ix_authentication_identities_user_id",
        "authentication_identities",
        ["user_id"],
        unique=False,
    )

    # Remove the legacy organization relationship from users.
    op.drop_constraint(
        "users_organization_id_fkey",
        "users",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_users_organization_id",
        table_name="users",
    )

    op.drop_constraint(
        "uq_user_organization_email",
        "users",
        type_="unique",
    )

    op.drop_column("users", "organization_id")
    op.drop_column("users", "role")

    # Apply the current global email uniqueness rule.
    op.create_unique_constraint(
        "uq_user_email",
        "users",
        ["email"],
    )

    op.create_check_constraint(
        "ck_user_email_lowercase",
        "users",
        "email = lower(email)",
    )


def downgrade() -> None:
    """Restore the legacy schema only when it is safe to do so."""

    connection = op.get_bind()

    existing_users = connection.execute(
        sa.text("SELECT COUNT(*) FROM users")
    ).scalar_one()

    existing_memberships = connection.execute(
        sa.text("SELECT COUNT(*) FROM organization_memberships")
    ).scalar_one()

    existing_identities = connection.execute(
        sa.text("SELECT COUNT(*) FROM authentication_identities")
    ).scalar_one()

    if (
        existing_users > 0
        or existing_memberships > 0
        or existing_identities > 0
    ):
        raise RuntimeError(
            "Downgrade aborted: users, memberships or authentication "
            "identities exist. A data migration is required before "
            "restoring the legacy schema."
        )

    # Remove authentication identities.
    op.drop_index(
        "ix_authentication_identities_user_id",
        table_name="authentication_identities",
    )
    op.drop_table("authentication_identities")

    # Remove organization memberships.
    op.drop_index(
        "ix_organization_memberships_user_id",
        table_name="organization_memberships",
    )
    op.drop_index(
        "ix_organization_memberships_organization_id",
        table_name="organization_memberships",
    )
    op.drop_table("organization_memberships")

    # Restore the legacy user schema.
    op.drop_constraint(
        "ck_user_email_lowercase",
        "users",
        type_="check",
    )

    op.drop_constraint(
        "uq_user_email",
        "users",
        type_="unique",
    )

    op.add_column(
        "users",
        sa.Column(
            "organization_id",
            sa.Uuid(),
            nullable=True,
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=30),
            nullable=True,
        ),
    )

    op.alter_column(
        "users",
        "organization_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )

    op.alter_column(
        "users",
        "role",
        existing_type=sa.String(length=30),
        nullable=False,
    )

    op.create_foreign_key(
        "users_organization_id_fkey",
        "users",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index(
        "ix_users_organization_id",
        "users",
        ["organization_id"],
        unique=False,
    )

    op.create_unique_constraint(
        "uq_user_organization_email",
        "users",
        ["organization_id", "email"],
    )
