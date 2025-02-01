"""
Script to test the correctness of the latest dates returned by the API.
"""
import os
from datetime import datetime
import requests
from utils.handle_datetimes import get_today_utc_date_in_timezone

from utils.handle_emails import notify_developer

try:
    response = requests.get(os.getenv("PING_URL") + "/api/analytics/get_dates?api_key=" + os.getenv("API_KEY"))
    if response.status_code > 200:
        raise Exception(f"Erroneous status code received: {response.status_code}")
    response.raise_for_status()
    jsonResponse = response.json()

    last_date = jsonResponse[-1]["date_string"]
    today_utc = get_today_utc_date_in_timezone("America/New_York")
    if last_date != today_utc:
      raise Exception(f"The latest date {last_date} from the API is incorrect. Today is {today_utc}")
except Exception as e:  # pylint: disable=W0703
    print(f"test-api.py reported an error: {e}")
    notify_developer(
        body=(
            f"Test API job reported an error at {datetime.utcnow()} UTC time: \n {e}"
        )
    )
