"""Run the background worker.

Connects with WORKER_DATABASE_URL, a login that holds the eka_worker role,
and switches to that role in every transaction.

Run from the backend folder:
    python -m scripts.run_worker            one pass
    python -m scripts.run_worker --watch    keep polling
"""

import argparse
import logging
import os
import socket
import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.history_service import purge_expired
from app.services.worker import WORKER_ROLE, run_once

# Old questions are deleted once an hour (and at start).
PURGE_EVERY_SECONDS = 3600


def purge_questions(engine) -> int:
    with Session(engine) as db:
        db.execute(text(f"SET LOCAL ROLE {WORKER_ROLE}"))
        removed = purge_expired(db)
        db.commit()
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--batch", type=int, default=5)
    arguments = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if not settings.WORKER_DATABASE_URL:
        print(
            "WORKER_DATABASE_URL is not set: it must name a login that "
            "holds the eka_worker role.",
            file=sys.stderr,
        )
        return 1

    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    engine = create_engine(settings.WORKER_DATABASE_URL, pool_pre_ping=True)

    last_purge = 0.0
    try:
        while True:
            if time.monotonic() - last_purge >= PURGE_EVERY_SECONDS:
                try:
                    removed = purge_questions(engine)
                    logging.info("worker %s: %s old questions deleted", worker_id, removed)
                except Exception as error:  # the queue keeps running
                    logging.warning("question purge failed: %s", type(error).__name__)
                last_purge = time.monotonic()

            outcome = run_once(
                engine, worker_id=worker_id, limit=arguments.batch
            )
            logging.info("worker %s: %s", worker_id, outcome)

            if not arguments.watch:
                return 0

            if not any(outcome.values()):
                time.sleep(arguments.interval)

    except KeyboardInterrupt:
        return 0

    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
