"""Wait until PostgreSQL accepts connections (used by the Docker entrypoint before the migrations).

Usage: python -m scripts.wait_for_db [--timeout SECONDS]
"""

import argparse
import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Espera o PostgreSQL aceitar conexões.")
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args(argv)

    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    deadline = time.monotonic() + args.timeout
    try:
        while True:
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                print("wait_for_db: PostgreSQL is ready")
                return
            except OperationalError:
                if time.monotonic() >= deadline:
                    sys.exit(f"wait_for_db: PostgreSQL not reachable after {args.timeout:.0f}s")
                time.sleep(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
