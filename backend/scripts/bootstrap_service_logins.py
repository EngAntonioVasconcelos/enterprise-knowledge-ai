"""Create the logins of the background services (Phase 10).

Run after the migrations, as the administrator, because the roles they
switch to (eka_worker, eka_mailer) are created by migrations.

- eka_worker_login: the worker and the data gateway. It may only switch to
  eka_worker (SET ROLE), which is how both connect in every transaction.
- eka_mailer_login: the e-mail dispatcher. It may only switch to
  eka_mailer.

Neither login inherits anything: a connection that has not switched role
can read and change nothing. Not superusers, no BYPASSRLS.

Environment:
    EKA_ADMIN_DATABASE_URL  administrator connection
    EKA_WORKER_PASSWORD     password for eka_worker_login (new role only)
    EKA_MAILER_PASSWORD     password for eka_mailer_login (new role only)

A login whose password is not given and that does not exist yet is
skipped. An existing login keeps its password; its attributes and its
single membership are enforced. Nothing secret is printed.
"""

import os
import sys

from psycopg import sql
from sqlalchemy import create_engine


ATTRIBUTES = (
    "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT"
)
# login role -> (the only role it may switch to, password variable)
LOGINS = {
    "eka_worker_login": ("eka_worker", "EKA_WORKER_PASSWORD"),
    "eka_mailer_login": ("eka_mailer", "EKA_MAILER_PASSWORD"),
}


def _exists(cursor, role: str) -> bool:
    cursor.execute("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s", (role,))
    return cursor.fetchone() is not None


def main() -> int:
    admin_url = os.environ.get("EKA_ADMIN_DATABASE_URL")
    if not admin_url:
        print("EKA_ADMIN_DATABASE_URL must be set.", file=sys.stderr)
        return 1

    engine = create_engine(admin_url)
    connection = engine.raw_connection()
    done: list[str] = []
    try:
        with connection.cursor() as cursor:
            for login, (target, password_name) in LOGINS.items():
                if not _exists(cursor, target):
                    print(f"Role {target} is missing: run the migrations first.", file=sys.stderr)
                    connection.rollback()
                    return 1
                password = os.environ.get(password_name)
                if _exists(cursor, login):
                    cursor.execute(
                        sql.SQL("ALTER ROLE {role} {attributes}").format(
                            role=sql.Identifier(login), attributes=sql.SQL(ATTRIBUTES)
                        )
                    )
                    done.append(f"{login}: attributes enforced")
                elif password:
                    cursor.execute(
                        sql.SQL("CREATE ROLE {role} {attributes} PASSWORD {password}").format(
                            role=sql.Identifier(login),
                            attributes=sql.SQL(ATTRIBUTES),
                            password=sql.Literal(password),
                        )
                    )
                    done.append(f"{login}: created")
                else:
                    done.append(f"{login}: skipped ({password_name} not set)")
                    continue
                # Only switching to its own role: nothing inherited.
                cursor.execute(
                    sql.SQL("GRANT {target} TO {role} WITH INHERIT FALSE, SET TRUE").format(
                        target=sql.Identifier(target), role=sql.Identifier(login)
                    )
                )
        connection.commit()
    finally:
        connection.close()
        engine.dispose()

    for line in done:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
