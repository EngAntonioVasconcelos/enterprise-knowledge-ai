# Database setup

How the PostgreSQL database is prepared, and the rules that keep every
environment identical.

## Roles

| Role | Login | Created by | Purpose |
| --- | --- | --- | --- |
| eka_runtime | yes | scripts/bootstrap_database.py | The running application. Not a superuser, no BYPASSRLS. |
| eka_rls_helper | no | migration 9a71c4d2e6b8 | Owns the private row-level security helper functions. |
| eka_platform_recovery | no | migration 4e76afd54850 | Capability to run the owner recovery function. |
| administrator | yes | the PostgreSQL installation | Runs the bootstrap script and the migrations. |

## Preparing a new environment

Run from the backend folder, with the virtual environment active.

1. Create an empty database.
2. Set EKA_ADMIN_DATABASE_URL (administrator connection) and
   EKA_RUNTIME_PASSWORD (password for the application role), then run:

        python scripts/bootstrap_database.py

3. Set MIGRATION_DATABASE_URL to the administrator connection and run:

        python -m alembic upgrade head

The bootstrap script is safe to run again: for an existing role it only
enforces the security attributes and keeps the password.

## Integration tests

Integration tests use a disposable PostgreSQL that keeps its data in
memory, so every start is a clean installation.

        docker compose -f ../infrastructure/test-db/docker-compose.yml up -d --wait
        python scripts/prepare_test_database.py
        python -m pytest

The test fixture refuses to run as a privileged role or against a schema
that is not at the latest migration. Locally, an unavailable database
skips the integration tests; in CI it fails them.

## Rules for new migrations

- A new table is not accessible to eka_runtime until a migration grants
  it. There are no default privileges. Grant only what the application
  needs, in the same migration that creates the table.
- Tables that hold tenant data enable and force row-level security in
  the migration that creates them.
- Never grant DELETE or TRUNCATE to eka_runtime without a written reason.

## Known limitations

- Migrations run as a PostgreSQL superuser, because they create a role
  with BYPASSRLS. A dedicated migration role is deferred until the
  hosting platform is chosen.
- The eka_test_runtime role and the enterprise_knowledge_ai_test
  database are no longer used.
