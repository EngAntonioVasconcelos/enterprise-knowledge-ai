"""Every check a block runs before committing, in order (inside the container).

    docker compose -f ../infrastructure/dev/docker-compose.yml run --rm backend python -m scripts.block_checks

1. ruff (lint);
2. prepare the disposable test database (port 1999), then the whole test
   suite against it;
3. the development database (port 1996): make sure the runtime role exists,
   apply the migrations and confirm the models and the database agree.

It stops at the first failure and returns its exit code, so nothing is
committed after a failed check. It refuses to touch any database other than
the development one on port 1996. Nothing secret is printed.
"""

import os
import subprocess
import sys

from sqlalchemy.engine import make_url

from app.core.config import settings


DEV_PORT = 1996

STEPS = (
    ("lint", [sys.executable, "-m", "ruff", "check", "."]),
    ("test database", [sys.executable, "scripts/prepare_test_database.py"]),
    ("tests", [sys.executable, "-m", "pytest", "-q", "--tb=line", "-rxX"]),
    ("development database role", "bootstrap"),
    ("migrations", [sys.executable, "-m", "alembic", "upgrade", "head"]),
    ("models match the database", [sys.executable, "-m", "alembic", "check"]),
)


def bootstrap_environment() -> dict | None:
    admin = make_url(settings.MIGRATION_DATABASE_URL)
    runtime = make_url(settings.DATABASE_URL)
    if admin.port != DEV_PORT or runtime.port != DEV_PORT:
        print(f"PAROU: MIGRATION_DATABASE_URL e DATABASE_URL tem de usar a porta {DEV_PORT}")
        return None
    print(f"Base de desenvolvimento: porta {DEV_PORT}, base {admin.database}")
    return dict(
        os.environ,
        EKA_ADMIN_DATABASE_URL=admin.render_as_string(hide_password=False),
        EKA_RUNTIME_PASSWORD=runtime.password or "",
    )


def main() -> int:
    for name, command in STEPS:
        print(f"\n== {name} ==", flush=True)
        environment = None
        if command == "bootstrap":
            environment = bootstrap_environment()
            if environment is None:
                return 1
            command = [sys.executable, "scripts/bootstrap_database.py"]
        code = subprocess.call(command, env=environment)
        if code != 0:
            print(f"\nPAROU: o passo '{name}' falhou (codigo {code}).")
            return code
    print("\nTodas as verificacoes passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
