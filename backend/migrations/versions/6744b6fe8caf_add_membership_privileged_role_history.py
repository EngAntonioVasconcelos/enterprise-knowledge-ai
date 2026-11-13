"""add membership privileged role history

Revision ID: 6744b6fe8caf
Revises: 248f338e700f
Create Date: 2026-11-11 00:40:05.815100

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6744b6fe8caf'
down_revision: Union[str, Sequence[str], None] = '248f338e700f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "organization_memberships",
        sa.Column(
            "has_held_privileged_role",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    # Preserve the privileged status of existing owners and admins.
    op.execute(
        """
        UPDATE organization_memberships
        SET has_held_privileged_role = TRUE
        WHERE role IN ('owner', 'admin')
        """
    )

    op.create_check_constraint(
        "ck_membership_privileged_role_history",
        "organization_memberships",
        "role NOT IN ('owner', 'admin') "
        "OR has_held_privileged_role = TRUE",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_membership_privileged_role_history",
        "organization_memberships",
        type_="check",
    )

    op.drop_column(
        "organization_memberships",
        "has_held_privileged_role",
    )
