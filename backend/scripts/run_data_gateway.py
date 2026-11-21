"""Run the data gateway (AL-4), the only process that queries customer
databases. Needs WORKER_DATABASE_URL, the master private key and
DATA_GATEWAY_TOKEN. Listens on the private network only.

Run from the backend folder:
    python -m scripts.run_data_gateway
"""

import argparse
import logging
import sys

import uvicorn

from app.core.config import settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8100)
    arguments = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    missing = [
        name
        for name in ("WORKER_DATABASE_URL", "CREDENTIALS_MASTER_PRIVATE_KEY", "DATA_GATEWAY_TOKEN")
        if not getattr(settings, name)
    ]
    if missing:
        print(f"The data gateway needs: {', '.join(missing)}", file=sys.stderr)
        return 1
    # No access log: the request bodies never reach the log either way.
    uvicorn.run(
        "app.services.data_gateway:app",
        host=arguments.host,
        port=arguments.port,
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
