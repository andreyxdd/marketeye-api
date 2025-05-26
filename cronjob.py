"""
Script to set and run analytics-computing cronjobs.
The idea is to compute and insert stocks analytics every trading day (often Monday to Friday)

Raises:
    Exception: If asyncio is not imported properly use trollius
"""

import sys

from time import time
from db.crud.tracking import put_top_tickers
from db.mongodb import connect as connect_mongo, get_database as get_mongo_database, close as close_mongo
from db.redis import RedisCache
from db.crud.analytics import compute_base_analytics_and_insert, remove_base_analytics
from db.crud.scrapes import remove_scrapes
from utils.handle_emails import notify_developer
from utils.handle_datetimes import (
    get_today_utc_date_in_timezone,
    get_past_date,
    get_epoch,
)
# from utils.handle_external_apis import get_ticker_base_analytics
from utils.handle_validation import validate_date_string

try:
    import asyncio
except ImportError:
    import trollius as asyncio


cache = RedisCache()
cache.connect()

async def run_crud_ops(date_to_insert: str, date_to_remove: str) -> str:
    """
    Method to run certain crud operations on the analytics collection.

    Args:
        date_to_insert (str):
            date, for which new base analytics is computed and inserted into db
        date_to_remove (str):
            date, for which old base analytics is removed from db
    """

    # connecting mongo db and getting its connection string
    await connect_mongo()
    conn = await get_mongo_database()

    msg_compute = await compute_base_analytics_and_insert(conn, date_to_insert)

    await remove_base_analytics(conn, date_to_remove)
    await remove_base_analytics(conn, date_to_remove, "tracking")
    await remove_scrapes(conn, date_to_remove)

    msg_track = await put_top_tickers(conn, date_to_insert)

    # disconneting mongo db
    await close_mongo()

    return msg_compute + "\n\n" + msg_track
    # get_ticker_base_analytics("AAPL", "2025-04-09", 45, 15, True)
    # return "done"


async def cronjob():
    """
    Function that defines the cronjob:
        - first, todays date is found (in NY time zone with respect to UTC)
        - then, past date (3 month ago) is found
        - next, the crud operations are run for the above dates.

    The functions also notifies developer about the results of the cronjob.
    """

    print("\n--------------------------------------------------------")
    print("Running analytics cronjob ...\n")
    start_time = time()

    today_utc = get_today_utc_date_in_timezone("America/New_York")
    yesterday_utc = get_past_date(1, today_utc)

    try:
        target_dates = [yesterday_utc, today_utc]
        if len(sys.argv) > 1:
            sys.argv.pop(0)
            target_dates = sys.argv

        print("Cronjob target dates are:")
        print(target_dates)

        for curr_date in target_dates:
            validate_date_string(curr_date)
            past_date = get_past_date(91, curr_date)
            msg = await run_crud_ops(curr_date, past_date)

            # notify_developer(
            #     body="The analytics cronjob has completed successfully: "
            #     + f"{curr_date} (epoch: {get_epoch(curr_date)})"
            #     + "\n\n----------------------- Logs ---------------------------\n\n"
            #     + f"{msg}"
            #     + "\n\n--------------------------------------------------------"
            # )

    except Exception as e:  # pylint: disable=W0703
        print("cronjob.py: Something went wrong.")
        print("Error message:", e)
        notify_developer(
            body=f"Analytics cronjob reported an error: {curr_date} ({get_epoch(curr_date)})"
            + f" with error message:\n\n {e}",
            subject="Cronjob Report",
        )

    print(f"\nAnalytics cronjob finished on {round(time() - start_time, 2)} seconds")
    print("--------------------------------------------------------")


if __name__ == "__main__":
    # Blocking execution when Ctrl+C (Ctrl+Break on Windows) is pressed
    try:
        asyncio.run(cronjob())  # initiating a cronjob
    except (KeyboardInterrupt, SystemExit):
        pass
