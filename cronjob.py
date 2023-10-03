"""
Script to set and run analytics-computing cronjobs.
The idea is to compute and insert stocks analytics every trading day (often Monday to Friday)

Raises:
    Exception: If asyncio is not imported properly use trollius
"""

import logging
from time import time
from db.crud.tracking import put_top_tickers
from db.insert.macd import count_frequencies_by_macd, insert_top_by_macd
from db.insert.timeseries import compute_timeseries_and_insert
from db.mongodb import connect, get_database, close
from db.crud.analytics import compute_base_analytics_and_insert, remove_base_analytics
from db.crud.scrapes import remove_scrapes
from utils.handle_emails import notify_developer
from utils.handle_datetimes import (
    get_today_utc_date_in_timezone,
    get_past_date,
    get_epoch,
)
from utils.handle_validation import validate_date_string

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('CRONJOB')

try:
    import asyncio
except ImportError:
    import trollius as asyncio


async def analyze_and_insert(date_to_insert: str) -> str:
    """

    """

    # connecting mongo db and getting its connection string
    await connect()
    conn = await get_database()

    msg = await compute_timeseries_and_insert(conn, date_to_insert)

    await insert_top_by_macd(conn, date_to_insert)

    await count_frequencies_by_macd(conn, date_to_insert)

    # await analyze_by_criteria(conn)
    # await analyze_by_frequency(conn)

    # msg_compute = await compute_base_analytics_and_insert(conn, date_to_insert)
    # msg_track = await put_top_tickers(conn, date_to_insert)

    # await remove_base_analytics(conn, date_to_remove)
    # await remove_base_analytics(conn, date_to_remove, "tracking")
    # await remove_scrapes(conn, date_to_remove)

    # disconneting mongo db
    await close()

    return msg


async def cronjob():
    """
    Method to run analytics on the EOD data for the given
    date (in NY time zone with respect to UTC) and
    then insert the results into the DB.
    The cronjob report is sent to the developer.
    """

    log.info("Starting the cronjob ...")
    start_time = time()

    try:
<< << << < Updated upstream
   target_dates = [get_today_utc_date_in_timezone("America/New_York")]
    if len(sys.argv) > 1:
        sys.argv.pop(0)
        target_dates = sys.argv

    print("Cronjob target dates are;")
    print(target_dates)

    for curr_date in target_dates:
        validate_date_string(curr_date)
        past_date = get_past_date(91, curr_date)
        msg = await run_crud_ops(curr_date, past_date)

        notify_developer(
            body="The analytics cronjob has completed successfully."
            + " Check MongoDB to see if today base analytics data"
            + f", {curr_date} ({get_epoch(curr_date)}), was inserted."
            + "\n\n----------------------- Logs ---------------------------\n\n"
            + f"{msg}"
            + "\n\n--------------------------------------------------------"
        )
== == == =
   # get_today_utc_date_in_timezone("America/New_York")
   curr_date = "2023-05-30"
    msg = await analyze_and_insert(curr_date)

    notify_developer(
        body="Today cronjob has completed successfully."
        + " Check MongoDB to see if today data"
        + f", {curr_date} ({get_epoch(curr_date)}), was inserted."
        + "\n\n----------------------- Logs ---------------------------\n\n"
        + f"{msg}"
        + "\n\n--------------------------------------------------------"
    )
>>>>>> > Stashed changes

   except Exception as e:  # pylint: disable=W0703
        log.error(e)
        notify_developer(
            body=f"Cronjob reported an error: {curr_date} ({get_epoch(curr_date)})"
            + f" with error message:\n\n {e}",
            subject="Cronjob Report",
        )

    log.info(
        "The cronjob finished in "
        +
        f"{round(time() - start_time, 2)} seconds"
    )


if __name__ == "__main__":
    # Blocking execution when Ctrl+C (Ctrl+Break on Windows) is pressed
    try:
        asyncio.run(cronjob())  # initiating a cronjob
    except (KeyboardInterrupt, SystemExit):
        pass
