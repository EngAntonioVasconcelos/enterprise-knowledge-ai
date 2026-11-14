import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.db.context import set_organization_context
from app.models import EmailOutbox, OrganizationInvitation
from app.services.email_outbox_service import dispatch_pending_emails
from app.services.invitation_service import (
    create_invitation,
    revoke_invitation,
)
from scripts.prepare_test_database import TEST_ADMIN_URL
from tests.integration.test_postgres_rls import (
    _authenticate,
    _create_organization,
    _create_user,
)


pytestmark = pytest.mark.integration


class RecordingSender:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)


@pytest.fixture
def outbox_db(postgres_engine):
    # One administrator connection that plays both sides: the application
    # (SET ROLE eka_runtime) and the dispatcher (SET ROLE eka_mailer), so
    # both see the same uncommitted data. Everything is rolled back.
    engine = create_engine(TEST_ADMIN_URL)
    connection = engine.connect()
    transaction = connection.begin()
    db = sessionmaker(
        bind=connection,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )()

    try:
        db.execute(text("SET ROLE eka_runtime"))
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def _as(db, role):
    db.flush()
    db.execute(text(f"SET ROLE {role}"))


def _invite(db, email=None):
    owner = _create_user(db, "outbox-owner")
    organization = _create_organization(db, owner)
    _authenticate(db, owner)
    set_organization_context(db, organization_id=organization.id)
    invitation, token = create_invitation(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        email=email or f"guest-{uuid.uuid4().hex}@example.com",
        role="member",
    )
    db.flush()
    # Plain values: as eka_mailer the session cannot reload the invitation.
    invitation = SimpleNamespace(
        id=invitation.id,
        email=invitation.email,
        expires_at=invitation.expires_at,
    )
    return owner, organization, invitation, token


def _emails(db):
    db.expire_all()
    return db.scalars(select(EmailOutbox)).all()


def _refused(db, statement, fragment):
    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            db.execute(statement)
    assert fragment in str(error.value.orig)


def test_invitation_email_is_queued_but_unreadable_by_the_application(
    outbox_db,
):
    db = outbox_db
    _, _, invitation, token = _invite(db)

    _refused(db, select(EmailOutbox.id), "permission denied")

    _as(db, "eka_mailer")
    [email] = [e for e in _emails(db) if e.reference_id == invitation.id]

    assert email.recipient == invitation.email
    assert f"#token={token}" in email.body


def test_application_queues_only_for_its_own_pending_invitations(
    outbox_db,
):
    db = outbox_db
    owner, organization, invitation, _ = _invite(db)
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)

    def queue(**overrides):
        values = dict(
            id=uuid.uuid4(),
            organization_id=organization.id,
            kind="invitation",
            reference_id=invitation.id,
            recipient=invitation.email,
            subject="Hello",
            body="Spam",
            expires_at=invitation.expires_at,
            created_at=datetime.now(timezone.utc),
        )
        values.update(overrides)
        return insert(EmailOutbox).values(**values)

    rls = "row-level security"
    # Somebody else's address, an invitation that does not exist, an expiry
    # the invitation does not have, and a second e-mail for the same one.
    _refused(db, queue(recipient="victim@example.com"), rls)
    _refused(db, queue(reference_id=uuid.uuid4()), rls)
    _refused(db, queue(expires_at=expires_at), rls)
    _refused(db, queue(), "uq_email_outbox_reference")

    revoke_invitation(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        invitation_id=invitation.id,
    )
    # Once the invitation is revoked, it accepts no e-mail at all.
    _refused(db, queue(kind="invitation", body="Again"), rls)


def test_dispatcher_sends_once_and_erases_the_link(outbox_db):
    db = outbox_db
    _, _, invitation, token = _invite(db)
    sender = RecordingSender()

    _as(db, "eka_mailer")
    first = dispatch_pending_emails(db, sender, from_address="eka@test")
    second = dispatch_pending_emails(db, sender, from_address="eka@test")

    assert first["sent"] >= 1
    assert second["sent"] == 0
    assert [m.recipient for m in sender.messages].count(invitation.email) == 1

    [email] = [e for e in _emails(db) if e.reference_id == invitation.id]
    assert email.sent_at is not None
    assert email.body is None


def test_outbox_rows_cannot_be_rewritten(outbox_db):
    db = outbox_db
    _, _, invitation, _ = _invite(db)
    _as(db, "eka_mailer")
    row = EmailOutbox.reference_id == invitation.id

    _refused(
        db,
        update(EmailOutbox).where(row).values(body="Something else"),
        "body can only be cleared",
    )
    _refused(
        db,
        update(EmailOutbox).where(row).values(recipient="x@example.com"),
        "permission denied",
    )

    db.execute(
        update(EmailOutbox)
        .where(row)
        .values(body=None, sent_at=datetime.now(timezone.utc))
    )

    _refused(
        db,
        update(EmailOutbox).where(row).values(attempts=1),
        "sent or cancelled email cannot change",
    )


def test_revoking_an_invitation_cancels_its_unsent_email(outbox_db):
    db = outbox_db
    owner, organization, invitation, _ = _invite(db)

    revoke_invitation(
        db,
        organization_id=organization.id,
        actor_user_id=owner.id,
        invitation_id=invitation.id,
    )

    _as(db, "eka_mailer")
    [email] = [e for e in _emails(db) if e.reference_id == invitation.id]
    assert email.cancelled_at is not None
    assert email.body is None


def test_the_mailer_reads_nothing_but_the_outbox(outbox_db):
    db = outbox_db
    _as(db, "eka_mailer")

    _refused(db, select(OrganizationInvitation.id), "permission denied")
    _refused(db, text("SELECT id FROM users"), "permission denied")


def test_the_application_cannot_become_the_mailer(postgres_db_session):
    db = postgres_db_session

    _refused(db, text("SET ROLE eka_mailer"), "permission denied")
