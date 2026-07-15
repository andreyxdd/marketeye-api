"""
Script to test the correctness of the latest dates returned by the API.

Compares each market's published latest date to LastCompletedSession
(provider probe), not calendar today.
"""
import os
import sys
from datetime import datetime

import pytz
import requests

from core.markets import MARKETS
from providers import get_market_data_provider
from utils.handle_telegram import notify_developer

CHECK_MARKETS = ("US", "TO")


def _calendar_end_for_market(market: str) -> str:
    tz = pytz.timezone(MARKETS[market]["timezone"])
    return datetime.now(tz).strftime("%Y-%m-%d")


def _assert_market_fresh(ping_url: str, api_key: str, market: str) -> None:
    response = requests.get(
        f"{ping_url}/api/analytics/get_dates?api_key={api_key}&market={market}",
        timeout=30,
    )
    if response.status_code > 200:
        raise RuntimeError(
            f"{market}: erroneous status code received: {response.status_code}"
        )
    response.raise_for_status()
    payload = response.json()
    if not payload:
        raise RuntimeError(f"{market}: empty dates payload from API")

    last_date = payload[-1]["date_string"]
    calendar_end = _calendar_end_for_market(market)
    provider = get_market_data_provider(market)
    last_session, _prior = provider.resolve_session_dates(calendar_end)
    if not last_session:
        raise RuntimeError(
            f"{market}: could not resolve LastCompletedSession "
            f"(calendar_end={calendar_end})"
        )
    if last_date != last_session:
        raise RuntimeError(
            f"{market}: latest date {last_date} from the API is incorrect. "
            f"LastCompletedSession is {last_session}"
        )


def run_test_api() -> None:
    ping_url = os.getenv("PING_URL", "").rstrip("/")
    api_key = os.getenv("API_KEY")
    if not ping_url or not api_key:
        raise RuntimeError("PING_URL and API_KEY must be configured")

    for market in CHECK_MARKETS:
        _assert_market_fresh(ping_url, api_key, market)


def main() -> int:
    try:
        run_test_api()
        print("test-api.py: latest analytics dates match LastCompletedSession")
        return 0
    except Exception as error:  # pylint: disable=broad-except
        print(f"test-api.py reported an error: {error}")
        notify_developer(
            subject="API freshness check failed",
            body=(
                f"Test API job reported an error at {datetime.utcnow()} UTC.\n\n"
                f"{error}"
            ),
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
