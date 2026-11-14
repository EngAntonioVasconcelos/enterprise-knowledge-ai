import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.email_outbox import EmailOutbox
from app.services import email_outbox_service
from app.services.email_outbox_service import (
    MAX_ATTEMPTS,
    dispatch_pending_emails,
    invitation_link,
)
from app.services.email_sender import (
    ConsoleEmailSender,
    EmailMessage,
    get_email_sender,
)


class RecordingSender:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)


class FailingSender:
    def send(self, message):
        raise ConnectionError("provider unavailable")


def _invite(client, email="Guest@Example.com"):
    unique = uuid.uuid4().hex[:8]
    organization = client.post(
        "/api/v1/organizations/",
        json={"name": f"Outbox Org {unique}", "slug": f"outbox-{unique}"},
    )
    assert organization.status_code == 201

    response = client.post(
        f"/api/v1/organizations/{organization.json()['id']}/invitations/",
        json={"email": email, "role": "member"},
    )
    assert response.status_code == 201
    return organization.json(), response.json()


def _outbox(db_session):
    db_session.expire_all()
    return db_session.scalars(select(EmailOutbox)).all()


def _dispatch(db_session, sender):
    outcome = dispatch_pending_emails(
        db_session, sender, from_address="no-reply@example.com"
    )
    db_session.commit()
    return outcome


def test_creating_an_invitation_enqueues_its_email(client, db_session):
    organization, invitation = _invite(client)

    [email] = _outbox(db_session)

    assert email.kind == "invitation"
    assert email.reference_id == uuid.UUID(invitation["id"])
    assert email.recipient == "guest@example.com"
    assert organization["name"] in email.subject
    assert invitation_link(invitation["token"]) in email.body
    assert (email.attempts, email.sent_at, email.cancelled_at) == (
        0,
        None,
        None,
    )


def test_the_link_carries_the_token_in_the_fragment(monkeypatch):
    monkeypatch.setattr(
        settings, "FRONTEND_BASE_URL", "https://app.example.com/"
    )

    assert invitation_link("abc") == (
        "https://app.example.com/invitations/accept#token=abc"
    )


def test_dispatch_sends_once_and_clears_the_body(client, db_session):
    _invite(client)
    sender = RecordingSender()

    assert _dispatch(db_session, sender) == {
        "sent": 1,
        "failed": 0,
        "cancelled": 0,
    }
    assert _dispatch(db_session, sender)["sent"] == 0

    [message] = sender.messages
    assert message.recipient == "guest@example.com"
    assert message.sender == "no-reply@example.com"
    assert "#token=" in message.body

    [email] = _outbox(db_session)
    assert email.sent_at is not None
    assert email.body is None


def test_failures_are_retried_then_given_up(client, db_session):
    _invite(client)

    for attempt in range(1, MAX_ATTEMPTS):
        assert _dispatch(db_session, FailingSender())["failed"] == 1
        [email] = _outbox(db_session)
        assert email.attempts == attempt
        assert email.last_error == "ConnectionError: provider unavailable"
        assert email.body is not None

    assert _dispatch(db_session, FailingSender())["cancelled"] == 1

    [email] = _outbox(db_session)
    assert email.attempts == MAX_ATTEMPTS
    assert email.cancelled_at is not None
    assert email.body is None


def test_an_expired_email_is_cancelled_without_sending(client, db_session):
    _invite(client)
    [email] = _outbox(db_session)
    email.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    sender = RecordingSender()

    assert _dispatch(db_session, sender)["cancelled"] == 1

    assert sender.messages == []
    [email] = _outbox(db_session)
    assert email.cancelled_at is not None
    assert email.body is None


def test_the_body_states_the_role_and_expiry():
    expires_at = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)

    subject, body = email_outbox_service.render_invitation_email(
        organization_name="Acme",
        role="admin",
        link="https://app.example.com/x",
        expires_at=expires_at,
    )

    assert subject == "You are invited to join Acme"
    assert "as admin" in body
    assert "2026-01-02 03:04 UTC" in body
    assert body.isascii()


def test_console_sender_prints_and_unknown_senders_are_refused(caplog):
    caplog.set_level(logging.WARNING, logger="eka.email")

    get_email_sender("console").send(
        EmailMessage(
            sender="a@example.com",
            recipient="b@example.com",
            subject="Hello",
            body="Body text",
        )
    )

    assert isinstance(get_email_sender("console"), ConsoleEmailSender)
    assert "DEVELOPMENT EMAIL" in caplog.text
    assert "Body text" in caplog.text

    with pytest.raises(ValueError):
        get_email_sender("carrier-pigeon")
