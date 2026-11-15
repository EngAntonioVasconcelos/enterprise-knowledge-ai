"""Create the development master key pair for connection credentials.

Writes CREDENTIALS_MASTER_PUBLIC_KEY and CREDENTIALS_MASTER_PRIVATE_KEY to
backend/.env and prints only the public key fingerprint: the private key is
never shown. Refuses to run if either name is already set, because
replacing the master key makes every stored credential unreadable
(rotation is a separate, deliberate procedure).

In production the master key lives in a KMS (Phase 10), not in a file.

Run from the backend folder:
    python -m scripts.generate_master_key
"""

import sys
from pathlib import Path

from app.core import credential_crypto as crypto


ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
NAMES = ("CREDENTIALS_MASTER_PUBLIC_KEY", "CREDENTIALS_MASTER_PRIVATE_KEY")


def main() -> int:
    existing = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    already = [
        name
        for name in NAMES
        if any(
            line.strip().startswith(f"{name}=")
            and line.strip() != f"{name}="
            for line in existing.splitlines()
        )
    ]
    if already:
        print(
            f"{', '.join(already)} already set in {ENV_FILE.name}: nothing "
            "changed. Replacing the master key would make every stored "
            "credential unreadable.",
            file=sys.stderr,
        )
        return 1

    public, private = crypto.generate_key_pair()
    lines = [
        line
        for line in existing.splitlines()
        if not any(line.strip() == f"{name}=" for name in NAMES)
    ]
    lines += [
        "",
        "# Connection credentials master key (development only; ADR-007).",
        "# The API needs only the public key; the worker needs both.",
        f"CREDENTIALS_MASTER_PUBLIC_KEY={crypto.encode_key(public)}",
        f"CREDENTIALS_MASTER_PRIVATE_KEY={crypto.encode_key(private)}",
    ]
    ENV_FILE.write_text("\n".join(lines).lstrip("\n") + "\n", encoding="utf-8")

    print(f"Master key written to {ENV_FILE.name}: {crypto.fingerprint(public)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
