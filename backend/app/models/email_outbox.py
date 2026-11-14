import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


EMAIL_KINDS = ("invitation",)


class EmailOutbox(Base):
    """An e-mail waiting to be sent, written in the same transaction as the
    change that causes it.

    The application can only add rows, and only for a pending invitation of
    an organization it manages (migration b3f8d2a6c9e4). A separate
    dispatcher, running as eka_mailer, sends them. The body carries a
    one-time link, so it is cleared once the e-mail is sent or cancelled.
    """

    __tablename__ = "email_outbox"

    __table_args__ = (
        UniqueConstraint(
            "reference_id",
            "kind",
            name="uq_email_outbox_reference",
        ),
        CheckConstraint(
            "kind IN ('invitation')",
            name="ck_email_outbox_kind",
        ),
        CheckConstraint(
            "(sent_at IS NULL AND cancelled_at IS NULL) OR body IS NULL",
            name="ck_email_outbox_body_cleared",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_email_outbox_organization_id_organizations",
        ),
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    reference_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )

    recipient: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    subject: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )

    last_error: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
