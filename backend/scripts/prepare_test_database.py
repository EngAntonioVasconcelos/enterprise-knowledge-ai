"""Prepare the disposable integration-test database.

Creates the runtime role and applies every migration to the PostgreSQL
started by infrastructure/test-db/docker-compose.yml. The credentials
are the local, throwaway ones declared in that file.
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine import make_url


BACKEND_DIR = Path(__file__).resolve().parents[1]

TEST_DATABASE = "eka_test"
TEST_RUNTIME_ROLE = "eka_runtime"
TEST_RUNTIME_PASSWORD = "local-test-runtime-only"

TEST_ADMIN_URL = os.environ.get(
    "EKA_TEST_ADMIN_DATABASE_URL",
    "postgresql+psycopg://eka_test_admin:local-test-admin-only"
    f"@127.0.0.1:1999/{TEST_DATABASE}",
)

TEST_RUNTIME_URL = (
    make_url(TEST_ADMIN_URL)
    .set(username=TEST_RUNTIME_ROLE, password=TEST_RUNTIME_PASSWORD)
    .render_as_string(hide_password=False)
)


def main() -> int:
    if make_url(TEST_ADMIN_URL).database != TEST_DATABASE:
        print(
            f"Refusing to run: the target database must be {TEST_DATABASE}.",
            file=sys.stderr,
        )
        return 1

    environment = dict(
        os.environ,
        EKA_ADMIN_DATABASE_URL=TEST_ADMIN_URL,
        EKA_RUNTIME_PASSWORD=TEST_RUNTIME_PASSWORD,
        MIGRATION_DATABASE_URL=TEST_ADMIN_URL,
    )
    environment.setdefault("DATABASE_URL", TEST_RUNTIME_URL)

    commands = (
        [sys.executable, "scripts/bootstrap_database.py"],
        [sys.executable, "-m", "alembic", "upgrade", "head"],
    )

    for command in commands:
        subprocess.run(command, check=True, cwd=BACKEND_DIR, env=environment)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
