"""How an e-mail leaves the platform.

The provider is chosen together with hosting (Phase 8). Until then the only
sender writes messages to the console, for development.
"""

import logging
from dataclasses import dataclass
from typing import Protocol


logger = logging.getLogger("eka.email")


@dataclass(frozen=True)
class EmailMessage:
    sender: str
    recipient: str
    subject: str
    body: str


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None:
        """Deliver the message or raise; never return on failure."""


class ConsoleEmailSender:
    """Development only: prints the message, one-time link included."""

    def send(self, message: EmailMessage) -> None:
        logger.warning(
            "DEVELOPMENT EMAIL (not delivered)\n"
            "From: %s\nTo: %s\nSubject: %s\n\n%s",
            message.sender,
            message.recipient,
            message.subject,
            message.body,
        )


SENDERS = {
    "console": ConsoleEmailSender,
}


def get_email_sender(name: str) -> EmailSender:
    try:
        return SENDERS[name]()
    except KeyError:
        raise ValueError(f"Unknown email sender: {name}") from None
