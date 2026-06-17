"""Infra health probe for /healthz and /readyz."""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.handle_telegram import notify_developer

HEALTHCHECK_TIMEOUT_SECONDS = 30


def _base_url(ping_url: Optional[str] = None) -> str:
    url = (ping_url or os.getenv("PING_URL") or "").rstrip("/")
    if not url:
        raise RuntimeError("PING_URL is not configured")
    return url


def _probe(path: str, ping_url: Optional[str] = None) -> tuple[int, str]:
    response = requests.get(
        f"{_base_url(ping_url)}{path}",
        timeout=HEALTHCHECK_TIMEOUT_SECONDS,
    )
    return response.status_code, response.text


def run_healthcheck(ping_url: Optional[str] = None) -> dict:
    """Probe liveness and readiness endpoints; raise on failure."""
    results = {}
    for path in ("/healthz", "/readyz"):
        status_code, body = _probe(path, ping_url=ping_url)
        results[path] = {"status_code": status_code, "body": body}
        if status_code != 200:
            raise RuntimeError(
                f"{path} returned HTTP {status_code}: {body[:500]}"
            )
    return results


def main() -> int:
    try:
        summary = run_healthcheck()
        print(f"healthcheck_monitor: ok {summary}")
        return 0
    except Exception as error:  # pylint: disable=broad-except
        print(f"healthcheck_monitor: failed: {error}")
        notify_developer(
            subject="Infra health check failed",
            body=str(error),
        )
        return 1


def _parse_args():
    parser = argparse.ArgumentParser(description="Probe API health endpoints")
    parser.add_argument(
        "--ping-url",
        default=None,
        help="Base URL override (defaults to PING_URL env var)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.ping_url:
        os.environ["PING_URL"] = args.ping_url
    sys.exit(main())
