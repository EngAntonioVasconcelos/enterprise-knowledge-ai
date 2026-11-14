"""Grant explicit runtime privileges and remove default privileges.

Revision ID: d7e2a9c41f05
Revises: 4e76afd54850
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d7e2a9c41f05"
down_revision: Union[str, Sequence[str], None] = "4e76afd54850"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Table privileges of the application runtime role, stated explicitly.
# A table that is not listed here is not accessible to the runtime.
RUNTIME_TABLE_PRIVILEGES = {
    "users": "SELECT, INSERT, UPDATE",
    "authentication_identities": "SELECT, INSERT, UPDATE",
    "organizations": "SELECT, INSERT, UPDATE",
    "organization_memberships": "SELECT, INSERT, UPDATE",
    "documents": "SELECT, INSERT, UPDATE",
    "platform_memberships": "SELECT",
    "organization_owner_recovery_events": "SELECT",
}


def upgrade() -> None:
    # Replace whatever the runtime holds on each table with the exact set.
    for table, privileges in RUNTIME_TABLE_PRIVILEGES.items():
        op.execute(
            f"REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM eka_runtime"
        )
        op.execute(
            f"GRANT {privileges} ON TABLE public.{table} TO eka_runtime"
        )

    # New tables and sequences must not become accessible automatically.
    # These statements apply to objects created by the role that runs
    # the migrations, and are no-ops where no default privileges exist.
    op.execute("""
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE ALL PRIVILEGES ON TABLES FROM eka_runtime;

        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE ALL PRIVILEGES ON SEQUENCES FROM eka_runtime;
    """)


def downgrade() -> None:
    # Before this revision the runtime privileges came from default
    # privileges configured by hand. Restore that behaviour.
    op.execute("""
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT SELECT, INSERT, UPDATE ON TABLES TO eka_runtime;

        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT SELECT, USAGE ON SEQUENCES TO eka_runtime;

        GRANT INSERT
        ON TABLE public.organization_owner_recovery_events
        TO eka_runtime;
    """)
