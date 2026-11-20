# The backend in a container (development)

## Why

On 20 November 2026 Windows Smart App Control started blocking an unsigned
library of the project (`psycopg_binary`), and any other compiled library
could follow. Running the backend tools in a Linux container takes the
Windows Python out of the way, gives the same environment as CI and as the
production servers (Phase 10), and replaces the manual workarounds
(PSYCOPG_IMPL, PATH, preparing the test database by hand).

## What there is

- `backend/Dockerfile`: Python 3.12 on Debian, the requirements, the code,
  a non-root user. The same image will be the base for production.
- `backend/scripts/container_env.py`: the entry point. It reads
  `backend/.env`, points `localhost` and `127.0.0.1` in every `*_URL`
  setting to `host.docker.internal` (the host machine, as Docker Desktop
  calls it), and runs the command. Nothing is printed; the file is never
  copied into the image (`.dockerignore`).
- The `backend` service in `infrastructure/dev/docker-compose.yml`, in the
  `tools` profile (so `docker compose up` does not start it). It mounts the
  `backend` folder over the code in the image, so changes are seen at once.

The databases stay where they are: the dev database on the host port 1996,
the test database on 1999, Ollama on 11434. The container reaches them
through `host.docker.internal`.

## Commands (from the repository root)

Build the image once, and again when `requirements.txt` changes:

    docker compose -f infrastructure/dev/docker-compose.yml build backend

Run anything in it, for example the tests or an evaluation:

    docker compose -f infrastructure/dev/docker-compose.yml run --rm backend python -m pytest -q
    docker compose -f infrastructure/dev/docker-compose.yml run --rm backend python -m scripts.evaluate_answers --limit 10

The test database must be running
(`docker compose -f infrastructure/test-db/docker-compose.yml up -d --wait`)
and prepared (`... run --rm backend python scripts/prepare_test_database.py`).

Git stays on Windows. Files are shared through the mount, which is slower
than a native disk: the tests take a little longer than on the host.

## How blocks check their work (since AJ-2a)

Blocks run every check inside the container with one command:

    docker compose -f infrastructure/dev/docker-compose.yml run --rm backend python -m scripts.block_checks

`scripts/block_checks.py` runs ruff, prepares the test database and runs the
tests, then makes sure the runtime role exists on the development database
(port 1996 only), applies the migrations and runs `alembic check`. It stops
at the first failure, and the block commits only if it returns 0. The
Windows Python is used only to write the block's files (standard library
only), and Git stays on Windows.
