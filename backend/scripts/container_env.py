"""Run a command inside the backend container with the host's addresses.

The .env file of the backend is written for the host machine: the dev
database at localhost:1996, Ollama at localhost:11434. Inside a container
"localhost" is the container itself, so this entry point reads the .env
file, changes localhost and 127.0.0.1 to host.docker.internal (Docker
Desktop's name for the host machine) in every *_URL setting, puts the
result in the environment (which wins over the file) and runs the command.

Settings already given to the container (compose environment) are kept.
Nothing is printed: the URLs carry passwords.

    python scripts/container_env.py python -m pytest -q
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import dotenv_values


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
HOST_MACHINE = "host.docker.internal"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def to_host_machine(url: str) -> str:
    """The same URL with a local host replaced by the host machine."""
    parts = urlsplit(url)
    if parts.hostname not in LOCAL_HOSTS:
        return url
    netloc = parts.netloc
    userinfo, _, hostport = netloc.rpartition("@")
    host = parts.hostname
    if hostport.startswith("["):
        hostport = hostport.replace(f"[{host}]", HOST_MACHINE, 1)
    else:
        hostport = hostport.replace(host, HOST_MACHINE, 1)
    netloc = f"{userinfo}@{hostport}" if userinfo else hostport
    return urlunsplit(parts._replace(netloc=netloc))


def container_environment(file_values: dict, environment: dict) -> dict:
    result = dict(environment)
    for key, value in file_values.items():
        if not key.endswith("_URL") or not value or key in environment:
            continue
        result[key] = to_host_machine(value)
    return result


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: container_env.py COMMAND [ARGS...]", file=sys.stderr)
        return 2
    values = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    environment = container_environment(values, dict(os.environ))
    os.execvpe(argv[0], argv, environment)
    return 0  # not reached


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
