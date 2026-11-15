"""Create OAUTH_STATE_SECRET, which signs the OAuth "state" (API only).

Writes it to backend/.env and prints nothing secret. If it is already
set, nothing changes. Replacing it later is harmless: only sign-ins
started before the change have to be started again.

Run from the backend folder:
    python -m scripts.generate_state_secret
"""

import secrets
import sys
from pathlib import Path


ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
NAME = "OAUTH_STATE_SECRET"


def main() -> int:
    existing = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    lines = existing.splitlines()
    if any(
        line.strip().startswith(f"{NAME}=") and line.strip() != f"{NAME}="
        for line in lines
    ):
        print(f"{NAME} already set in {ENV_FILE.name}: nothing changed.", file=sys.stderr)
        return 1

    lines = [line for line in lines if line.strip() != f"{NAME}="]
    lines += [
        "",
        "# Signs the OAuth state (docs/development/google-drive.md).",
        f"{NAME}={secrets.token_urlsafe(48)}",
    ]
    ENV_FILE.write_text("\n".join(lines).lstrip("\n") + "\n", encoding="utf-8")
    print(f"{NAME} written to {ENV_FILE.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
