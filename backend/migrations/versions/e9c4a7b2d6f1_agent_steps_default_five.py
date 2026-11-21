"""Five agent steps by default (AL-4h).

With databases the agent's path is: choose data or documents, write the
query, repair it once if the database refuses it, answer, check. Five
steps. The default goes from 4 to 5, and organizations still on the old
default (4) move to 5; a value an owner or admin chose otherwise is left
alone. Downgrade moves 5 back to 4.

Revision ID: e9c4a7b2d6f1
Revises: d7e3b9c5a2f8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9c4a7b2d6f1"
down_revision: Union[str, Sequence[str], None] = "d7e3b9c5a2f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("organizations", "agent_max_steps", server_default=sa.text("5"))
    op.execute("UPDATE public.organizations SET agent_max_steps = 5 WHERE agent_max_steps = 4")


def downgrade() -> None:
    op.execute("UPDATE public.organizations SET agent_max_steps = 4 WHERE agent_max_steps = 5")
    op.alter_column("organizations", "agent_max_steps", server_default=sa.text("4"))
