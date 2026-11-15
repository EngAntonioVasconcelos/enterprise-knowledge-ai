"""What an Owner or Admin narrows on a connection (its "scope").

A scope only restricts. A person reads a document when the source allows
it AND the connection's scope lets their role in; nothing here can grant
what the source does not (ADR-003, strict option of 2026-11-15).

Stored in the connection's settings:

    "scope": {
        "roles": ["owner", "admin", "member"],
        "file_types": ["pdf", "word", "google_docs"]
    }

A missing key means no restriction. Roles are enforced by the database
when it resolves readers (migration e7c3a9f5b2d8); file types by the sync
engine, which leaves excluded files out and removes them if they were in.
"""

import hashlib
import json

ROLES = ("owner", "admin", "member", "viewer")

FILE_TYPES = {
    "pdf": ("application/pdf",),
    "word": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    "text": ("text/plain", "text/markdown"),
    "google_docs": ("application/vnd.google-apps.document",),
    "google_slides": ("application/vnd.google-apps.presentation",),
}

SCOPE_KEYS = ("roles", "file_types")


def validate_scope(value) -> dict:
    """Raise ValueError unless value is a well-formed scope."""
    if not isinstance(value, dict):
        raise ValueError("scope must be an object")
    unknown = set(value) - set(SCOPE_KEYS)
    if unknown:
        raise ValueError(f"scope has unknown keys: {', '.join(sorted(unknown))}")

    for key, allowed in (("roles", ROLES), ("file_types", tuple(FILE_TYPES))):
        if key not in value:
            continue
        items = value[key]
        if not isinstance(items, list) or not items:
            raise ValueError(f"scope.{key} must be a non-empty list")
        if any(not isinstance(item, str) or item not in allowed for item in items):
            raise ValueError(
                f"scope.{key} accepts only: {', '.join(allowed)}"
            )
        if len(set(items)) != len(items):
            raise ValueError(f"scope.{key} has repeated values")
    return value


def allowed_mime_types(settings: dict) -> frozenset[str] | None:
    """The MIME types the scope lets in, or None when not restricted."""
    file_types = (settings.get("scope") or {}).get("file_types")
    if not file_types:
        return None
    return frozenset(
        mime for name in file_types for mime in FILE_TYPES.get(name, ())
    )


def file_types_fingerprint(settings: dict) -> str | None:
    """Changes when the file-type filter changes (None when there is none)."""
    file_types = (settings.get("scope") or {}).get("file_types")
    if not file_types:
        return None
    canonical = json.dumps(sorted(file_types), separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
