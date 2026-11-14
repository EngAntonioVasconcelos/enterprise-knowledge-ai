"""Send the e-mails waiting in the outbox.

Connects with MAILER_DATABASE_URL, a login that holds the eka_mailer role,
and switches to that role for every batch, so it can read and mark the
outbox and nothing else, whatever else the login could do.

Run from the backend folder:
    python -m scripts.send_outbox_emails            one batch
    python -m scripts.send_outbox_emails --watch    keep polling

Delivery is at least once: if the process stops between sending and
committing, the next run sends that e-mail again.
"""

import argparse
import logging
import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.email_outbox_service import dispatch_pending_emails
from app.services.email_sender import EmailSender, get_email_sender


def run_batch(engine: Engine, sender: EmailSender) -> dict[str, int]:
    with Session(engine) as db:
        db.execute(text("SET LOCAL ROLE eka_mailer"))
        outcome = dispatch_pending_emails(
            db,
            sender,
            from_address=settings.EMAIL_FROM,
        )
        db.commit()

    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=10.0)
    arguments = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if not settings.MAILER_DATABASE_URL:
        print(
            "MAILER_DATABASE_URL is not set: it must name a login that "
            "holds the eka_mailer role.",
            file=sys.stderr,
        )
        return 1

    engine = create_engine(settings.MAILER_DATABASE_URL, pool_pre_ping=True)
    sender = get_email_sender(settings.EMAIL_SENDER)

    try:
        while True:
            outcome = run_batch(engine, sender)
            logging.info("outbox: %s", outcome)

            if not arguments.watch:
                return 0

            time.sleep(arguments.interval)

    except KeyboardInterrupt:
        return 0

    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
