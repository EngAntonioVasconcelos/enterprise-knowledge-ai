"""Write e-mails to the outbox and send them.

Enqueueing happens in the transaction of the change that causes the e-mail,
so either both are saved or neither is. Sending happens afterwards, in the
dispatcher (scripts/send_outbox_emails.py).
"""

from datetime import datetime, timezone

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.email_outbox import EmailOutbox
from app.models.invitation import OrganizationInvitation
from app.models.organization import Organization
from app.services.email_sender import EmailMessage, EmailSender


MAX_ATTEMPTS = 5
BATCH_SIZE = 50


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    # SQLite, used by unit tests, returns naive datetimes.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def invitation_link(token: str) -> str:
    # The token travels in the fragment, which browsers never send to a
    # server, so it does not end up in access logs.
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{base}/invitations/accept#token={token}"


def render_invitation_email(
    *,
    organization_name: str,
    role: str,
    link: str,
    expires_at: datetime,
) -> tuple[str, str]:
    subject = f"You are invited to join {organization_name}"
    body = (
        f"You have been invited to join {organization_name} on "
        f"Enterprise Knowledge AI as {role}.\n"
        "\n"
        "Sign in with this e-mail address and open the link below to "
        "accept:\n"
        "\n"
        f"{link}\n"
        "\n"
        f"The invitation expires on {_as_aware(expires_at):%Y-%m-%d %H:%M} "
        "UTC and works only once. If you were not expecting it, you can "
        "ignore this message.\n"
    )
    return subject, body


def enqueue_invitation_email(
    db: Session,
    *,
    invitation: OrganizationInvitation,
    token: str,
) -> None:
    organization = db.get(Organization, invitation.organization_id)

    subject, body = render_invitation_email(
        organization_name=organization.name,
        role=invitation.role,
        link=invitation_link(token),
        expires_at=invitation.expires_at,
    )

    # A plain INSERT: the application may add to the outbox but not read
    # it, and an ORM insert could ask for the row back.
    db.execute(
        insert(EmailOutbox).values(
            organization_id=invitation.organization_id,
            kind="invitation",
            reference_id=invitation.id,
            recipient=invitation.email,
            subject=subject,
            body=body,
            expires_at=invitation.expires_at,
        )
    )


def dispatch_pending_emails(
    db: Session,
    sender: EmailSender,
    *,
    from_address: str,
    limit: int = BATCH_SIZE,
) -> dict[str, int]:
    """Send a batch of waiting e-mails and record the outcome.

    Rows are locked with SKIP LOCKED, so several dispatchers can run at once
    without sending the same e-mail twice. The caller commits.
    """
    outcome = {"sent": 0, "failed": 0, "cancelled": 0}

    emails = db.scalars(
        select(EmailOutbox)
        .where(
            EmailOutbox.sent_at.is_(None),
            EmailOutbox.cancelled_at.is_(None),
        )
        .order_by(EmailOutbox.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()

    for email in emails:
        now = _now()

        if _as_aware(email.expires_at) <= now:
            email.body = None
            email.cancelled_at = now
            outcome["cancelled"] += 1
            continue

        try:
            sender.send(
                EmailMessage(
                    sender=from_address,
                    recipient=email.recipient,
                    subject=email.subject,
                    body=email.body,
                )
            )

        except Exception as exc:
            email.attempts += 1
            email.last_error = f"{type(exc).__name__}: {exc}"[:500]

            if email.attempts >= MAX_ATTEMPTS:
                email.body = None
                email.cancelled_at = now
                outcome["cancelled"] += 1
            else:
                outcome["failed"] += 1

            continue

        email.body = None
        email.sent_at = now
        outcome["sent"] += 1

    db.flush()

    return outcome
