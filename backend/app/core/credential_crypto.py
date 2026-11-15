"""Encryption of connection credentials (ADR-007).

Two levels of X25519 key pairs, both used the same way ("sealing"):

- The master key pair belongs to the platform. Its public half is all the
  API holds; its private half only the worker (later, a KMS) holds.
- Each organization has its own key pair. The API creates it, seals the
  private half to the master public key and forgets it.

A credential is sealed to its organization's public key. The API can
therefore write credentials but never read one back: nothing it holds can
open them. The worker opens the organization key with the master private
key, then the credential with the organization key.

Sealing: a fresh ephemeral X25519 key, a shared secret with the recipient,
HKDF-SHA256 to an AES-256-GCM key, then AES-GCM with associated data that
binds the ciphertext to where it belongs (organization, connection). A
sealed value moved anywhere else does not open.
"""

import base64
import hashlib
import os
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


KEY_BYTES = 32
NONCE_BYTES = 12
SEAL_INFO = b"eka:seal:v1"


class CredentialCryptoError(Exception):
    """A sealed value could not be opened: wrong key, or tampered with."""


def _raw_public(key: X25519PublicKey) -> bytes:
    return key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


def _raw_private(key: X25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )


def _derive(shared: bytes, ephemeral: bytes, recipient: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_BYTES,
        salt=ephemeral + recipient,
        info=SEAL_INFO,
    ).derive(shared)


def encode_key(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_key(value: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(value.strip().encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("not a valid key") from exc
    if len(raw) != KEY_BYTES:
        raise ValueError("a key must be 32 bytes")
    return raw


def fingerprint(public_key: bytes) -> str:
    """Short, stable name of a public key (which key sealed a value)."""
    return "x25519:" + hashlib.sha256(public_key).hexdigest()[:16]


def generate_key_pair() -> tuple[bytes, bytes]:
    """Return (public, private), raw 32 bytes each."""
    private = X25519PrivateKey.generate()
    return _raw_public(private.public_key()), _raw_private(private)


def public_key_of(private_key: bytes) -> bytes:
    private = X25519PrivateKey.from_private_bytes(private_key)
    return _raw_public(private.public_key())


def seal(public_key: bytes, plaintext: bytes, *, context: bytes) -> bytes:
    recipient = X25519PublicKey.from_public_bytes(public_key)
    ephemeral = X25519PrivateKey.generate()
    ephemeral_public = _raw_public(ephemeral.public_key())

    key = _derive(ephemeral.exchange(recipient), ephemeral_public, public_key)
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, context)

    return ephemeral_public + nonce + ciphertext


def open_sealed(private_key: bytes, sealed: bytes, *, context: bytes) -> bytes:
    if len(sealed) < KEY_BYTES + NONCE_BYTES + 16:
        raise CredentialCryptoError("sealed value is too short")

    ephemeral_public = sealed[:KEY_BYTES]
    nonce = sealed[KEY_BYTES:KEY_BYTES + NONCE_BYTES]
    ciphertext = sealed[KEY_BYTES + NONCE_BYTES:]

    private = X25519PrivateKey.from_private_bytes(private_key)
    shared = private.exchange(X25519PublicKey.from_public_bytes(ephemeral_public))
    key = _derive(shared, ephemeral_public, public_key_of(private_key))

    try:
        return AESGCM(key).decrypt(nonce, ciphertext, context)
    except InvalidTag:
        raise CredentialCryptoError(
            "the value does not open with this key and context"
        ) from None


def organization_key_context(organization_id: uuid.UUID) -> bytes:
    return f"eka:organization-key:v1:{organization_id}".encode("ascii")


def credential_context(
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> bytes:
    return (
        f"eka:credential:v1:{organization_id}:{connection_id}"
    ).encode("ascii")
