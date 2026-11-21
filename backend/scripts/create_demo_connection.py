"""Connect the invented sales database to an organization (AL-4c).

Development only. Creates, in the development database (port 1996), a
PostgreSQL connection named "Vendas (exemplo)" to the demo database of
infrastructure/demo-db (port 1995, invented data, read-only login), seals
its credentials and asks the worker for its catalog. Running it again
keeps the connection, seals the same credentials again and refreshes the
catalog.

It acts as the organization's owner, through the same services and
row-level security as the API: the administrator account only finds the
organization and its owner. Nothing secret is printed.

Run from the backend folder, in the container:
    docker compose -f ../infrastructure/dev/docker-compose.yml run --rm backend python -m scripts.create_demo_connection
    ... --organization "Name or slug"   when there is more than one
"""

import argparse
import sys

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.context import set_identity_context, set_organization_context
from app.models.data_connection import DataConnection
from app.services.connection_service import create_connection
from app.services.credential_service import store_credentials
from app.services.sync_service import request_sync


DEV_PORT = 1996
NAME = "Vendas (exemplo)"
# The demo database, seen from the containers. Its credentials are for that
# local, throwaway database only (infrastructure/demo-db).
DEMO_SETTINGS = {
    "host": "host.docker.internal",
    "port": 1995,
    "database": "sales",
    "sslmode": "disable",
    "schemas": ["sales"],
}
DEMO_SECRET = {"username": "eka_reader", "password": "local-demo-reader-only"}

OWNERS_SQL = """
    SELECT o.id, o.name, o.slug, m.user_id, a.issuer, a.subject
    FROM organizations AS o
    JOIN organization_memberships AS m
      ON m.organization_id = o.id AND m.role = 'owner' AND m.is_active
    JOIN authentication_identities AS a
      ON a.user_id = m.user_id AND a.is_active
    WHERE o.status = 'active'
    ORDER BY o.name, a.last_authenticated_at DESC NULLS LAST
"""


def check_target(url: str | None) -> str | None:
    """None when the target is acceptable, otherwise the reason it is not."""
    if not url:
        return "MIGRATION_DATABASE_URL is not set"
    if make_url(url).port != DEV_PORT:
        return f"only the development database on port {DEV_PORT} is allowed"
    if not settings.DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS:
        return "DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS must be true (development)"
    return None


def choose(rows: list, wanted: str | None):
    """The organization (and one of its owners) to connect, or the reason
    none was chosen."""
    first = {}
    for row in rows:
        first.setdefault(row.id, row)
    organizations = list(first.values())
    if wanted:
        matches = [o for o in organizations if wanted.lower() in (o.name.lower(), o.slug.lower())]
        if len(matches) == 1:
            return matches[0], None
        return None, f"no single organization named {wanted!r}"
    if len(organizations) == 1:
        return organizations[0], None
    if not organizations:
        return None, "no active organization with an owner"
    names = ", ".join(repr(o.name) for o in organizations)
    return None, f"more than one organization ({names}): add --organization"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--organization")
    arguments = parser.parse_args()

    problem = check_target(settings.MIGRATION_DATABASE_URL)
    if problem:
        print(f"PAROU: {problem}.")
        return 1

    engine = create_engine(settings.MIGRATION_DATABASE_URL)
    try:
        with Session(engine) as db:
            if not db.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar():
                print("PAROU: the administrator account of the development database must be a superuser.")
                return 1
            organization, problem = choose(db.execute(text(OWNERS_SQL)).all(), arguments.organization)
            if problem:
                print(f"PAROU: {problem}.")
                return 1

            # From here on, as the owner: the API's role and policies.
            db.execute(text("SET LOCAL ROLE eka_runtime"))
            set_identity_context(
                db, issuer=organization.issuer, subject=organization.subject, user_id=organization.user_id
            )
            set_organization_context(db, organization_id=organization.id)

            connection = db.scalar(
                select(DataConnection).where(
                    DataConnection.organization_id == organization.id,
                    DataConnection.name == NAME,
                    DataConnection.status != "disconnected",
                )
            )
            if connection is None:
                connection = create_connection(
                    db,
                    organization_id=organization.id,
                    actor_user_id=organization.user_id,
                    provider="postgresql",
                    name=NAME,
                    settings=dict(DEMO_SETTINGS),
                )
                print(f"Connection created in {organization.name!r}: {NAME}")
            else:
                print(f"Connection already there in {organization.name!r}: {NAME}")
            store_credentials(
                db,
                organization_id=organization.id,
                connection_id=connection.id,
                secret=dict(DEMO_SECRET),
            )
            request_sync(db, connection=connection, actor_user_id=organization.user_id)
            db.commit()
            print("Credentials sealed; the worker will read the catalog in a few seconds.")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
