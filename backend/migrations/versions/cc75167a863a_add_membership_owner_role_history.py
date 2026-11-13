"""add membership owner role history

Revision ID: cc75167a863a
Revises: b42e8f1c7a63
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "cc75167a863a"
down_revision: Union[str, Sequence[str], None] = "b42e8f1c7a63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organization_memberships",
        sa.Column(
            "has_held_owner_role",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )

    op.execute(
        """
        UPDATE public.organization_memberships
        SET has_held_owner_role = TRUE
        WHERE role = 'owner'
        """
    )

    op.create_check_constraint(
        "ck_membership_owner_role_history",
        "organization_memberships",
        "role <> 'owner' OR has_held_owner_role = TRUE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_membership_owner_role_history",
        "organization_memberships",
        type_="check",
    )

    op.drop_column(
        "organization_memberships",
        "has_held_owner_role",
    )
