import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OrganizationKey(Base):
    """An organization's key pair (ADR-007).

    The public half seals the organization's credentials. The private half
    is stored sealed to the platform master key, which the API does not
    hold: only the worker can open it.
    """

    __tablename__ = "organization_keys"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_organization_keys_organization_id_organizations",
        ),
        primary_key=True,
    )

    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    sealed_private_key: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
    )

    master_key_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )


class ConnectionCredential(Base):
    """The secret of one connection, sealed to its organization's key."""

    __tablename__ = "connection_credentials"

    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "data_connections.id",
            ondelete="CASCADE",
            name="fk_connection_credentials_connection_id_data_connections",
        ),
        primary_key=True,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_connection_credentials_organization_id_organizations",
        ),
        nullable=False,
    )

    sealed: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    organization_key_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )
