"""
Script to test the correctness of the latest dates returned by the API.
"""
import os
import sys
from datetime import datetime

import requests

from utils.handle_datetimes import get_today_utc_date_in_timezone
from utils.handle_telegram import notify_developer


def run_test_api() -> None:
    ping_url = os.getenv("PING_URL", "").rstrip("/")
    api_key = os.getenv("API_KEY")
    if not ping_url or not api_key:
        raise RuntimeError("PING_URL and API_KEY must be configured")

    response = requests.get(
        f"{ping_url}/api/analytics/get_dates?api_key={api_key}",
        timeout=30,
    )
    if response.status_code > 200:
        raise RuntimeError(f"Erroneous status code received: {response.status_code}")
    response.raise_for_status()
    payload = response.json()

    last_date = payload[-1]["date_string"]
    today_utc = get_today_utc_date_in_timezone("America/New_York")
    if last_date != today_utc:
        raise RuntimeError(
            f"The latest date {last_date} from the API is incorrect. Today is {today_utc}"
        )


def main() -> int:
    try:
        run_test_api()
        print("test-api.py: latest analytics date matches expected session date")
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
