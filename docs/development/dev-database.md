# Development database in Docker

The development database runs in the container `eka-dev-pg`
(`infrastructure/dev/docker-compose.yml`), PostgreSQL 18.6, the same
version as CI and the test database. It listens only on `127.0.0.1:1996`.

Port 1996 is new on purpose: the previous development database (a
PostgreSQL installed on Windows, port 1997) is not touched. You switch
when you are ready, and you can switch back by changing two settings.

| Database | Where | Port | Data |
|---|---|---|---|
| Development | Docker, `eka-dev-pg` | 1996 | volume `eka_dev_pgdata`, kept |
| Previous development | PostgreSQL on Windows | 1997 | unchanged |
| Integration tests | Docker, `eka-test-pg` | 1999 | in memory, empty at every start |

## First start

From the repository root, in PowerShell:

1. Create your settings file and choose a password in it (an editor, not
   the terminal history):
   `Copy-Item infrastructure\dev\.env.example infrastructure\dev\.env`
2. Start the database and wait until it is healthy:
   `docker compose -f infrastructure/dev/docker-compose.yml up -d --wait`
3. From `backend`, with the `.venv` active, create the application role and
   apply the migrations. Set `EKA_ADMIN_DATABASE_URL`,
   `EKA_RUNTIME_PASSWORD` and `MIGRATION_DATABASE_URL` in that terminal
   yourself (administrator login from step 1, port 1996), then:
   `python scripts\bootstrap_database.py`
   `python -m alembic upgrade head`
4. When you want the API to use it, change `DATABASE_URL` and
   `MIGRATION_DATABASE_URL` in `backend/.env` to port 1996.

Never paste these values into a chat or a commit.

## Day to day

| What | Command |
|---|---|
| Start | `docker compose -f infrastructure/dev/docker-compose.yml up -d --wait` |
| Stop (data kept) | `docker compose -f infrastructure/dev/docker-compose.yml stop` |
| State | `docker compose -f infrastructure/dev/docker-compose.yml ps` |

`docker compose down -v` deletes the volume and every row in it: never
use it on this database without a backup.

## Next

The API and the worker join this compose file when the worker exists
(Phase 5). Production images come with hosting (Phase 10).
