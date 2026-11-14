"""Prepare a PostgreSQL database for the application.

Creates the login role used by the running application. It must run
once, as an administrator, before the Alembic migrations: they grant
privileges to this role but never create it.

Required environment variables:
    EKA_ADMIN_DATABASE_URL  administrator connection to the target database
    EKA_RUNTIME_PASSWORD    password for the eka_runtime role (new roles only)
"""

import os
import sys

from psycopg import sql
from sqlalchemy import create_engine


RUNTIME_ROLE = "eka_runtime"
ROLE_ATTRIBUTES = (
    "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
)


def main() -> int:
    admin_url = os.environ.get("EKA_ADMIN_DATABASE_URL")
    runtime_password = os.environ.get("EKA_RUNTIME_PASSWORD")

    if not admin_url or not runtime_password:
        print(
            "EKA_ADMIN_DATABASE_URL and EKA_RUNTIME_PASSWORD must be set.",
            file=sys.stderr,
        )
        return 1

    engine = create_engine(admin_url)
    connection = engine.raw_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s",
                (RUNTIME_ROLE,),
            )
            role_exists = cursor.fetchone() is not None

            if role_exists:
                # Enforce the security attributes; keep the password.
                cursor.execute(
                    sql.SQL("ALTER ROLE {role} {attributes}").format(
                        role=sql.Identifier(RUNTIME_ROLE),
                        attributes=sql.SQL(ROLE_ATTRIBUTES),
                    )
                )
            else:
                cursor.execute(
                    sql.SQL(
                        "CREATE ROLE {role} {attributes} PASSWORD {password}"
                    ).format(
                        role=sql.Identifier(RUNTIME_ROLE),
                        attributes=sql.SQL(ROLE_ATTRIBUTES),
                        password=sql.Literal(runtime_password),
                    )
                )

        connection.commit()
    finally:
        connection.close()
        engine.dispose()

    if role_exists:
        print(f"Role {RUNTIME_ROLE} already existed: attributes enforced.")
    else:
        print(f"Role {RUNTIME_ROLE} created.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
