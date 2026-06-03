"""
Script to set and run analytics-computing cronjobs.
The idea is to compute and insert stocks analytics every trading day (often Monday to Friday)

Raises:
    Exception: If asyncio is not imported properly use trollius
"""

import argparse
import sys

from time import time
from core.markets import MARKETS, list_markets, normalize_market
from db.crud.tracking import put_top_tickers
from db.mongodb import connect as connect_mongo, get_database as get_mongo_database, close as close_mongo
from db.crud.analytics import remove_base_analytics
from db.crud.scrapes import remove_scrapes
from utils.handle_emails import notify_developer
from utils.handle_datetimes import (
    get_today_utc_date_in_timezone,
    get_past_date,
    get_epoch,
)
from utils.handle_validation import validate_date_string
import services.analytics_service as analytics_service

try:
    import asyncio
except ImportError:
    import trollius as asyncio


async def run_crud_ops(date_to_insert: str, date_to_remove: str, market: str) -> str:
    await connect_mongo()
    conn = await get_mongo_database()

    msg_compute = await analytics_service.ingest_base_analytics_for_market(
        conn, date_to_insert, market=market
    )

    await remove_base_analytics(conn, date_to_remove, market=market)
    await remove_base_analytics(conn, date_to_remove, "tracking", market=market)
    if market == "US":
        await remove_scrapes(conn, date_to_remove)

    msg_track = await put_top_tickers(conn, date_to_insert, market=market)

    await close_mongo()

    return msg_compute + "\n\n" + msg_track


async def cronjob(markets=None):
    print("\n--------------------------------------------------------")
    print("Running analytics cronjob ...\n")
    start_time = time()

    markets_to_run = markets or list_markets()
    curr_date = None

    try:
        for market in markets_to_run:
            market = normalize_market(market)
            tz = MARKETS[market]["timezone"]
            today_utc = get_today_utc_date_in_timezone(tz)
            yesterday_utc = get_past_date(1, today_utc)
            target_dates = [today_utc, yesterday_utc]

            print(f"Market {market} ({tz}) target dates: {target_dates}")

            for curr_date in target_dates:
                validate_date_string(curr_date)
                past_date = get_past_date(91, curr_date)
                msg = await run_crud_ops(curr_date, past_date, market=market)
                print(msg)

    except Exception as e:  # pylint: disable=W0703
        print("cronjob.py: Something went wrong.")
        print("Error message:", e)
        notify_developer(
            body=f"Analytics cronjob reported an error: {curr_date} ({get_epoch(curr_date) if curr_date else 'n/a'})"
            + f" with error message:\n\n {e}",
            subject="Cronjob Report",
        )

    print(f"\nAnalytics cronjob finished on {round(time() - start_time, 2)} seconds")
    print("--------------------------------------------------------")


def _parse_args():
    parser = argparse.ArgumentParser(description="Run analytics cronjob")
    parser.add_argument(
        "dates",
        nargs="*",
        help="Optional target dates (YYYY-MM-DD). Overrides per-market today/yesterday.",
    )
    parser.add_argument(
        "--market",
        dest="markets",
        action="append",
        help="Market code to process (repeatable). Default: all configured markets.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.dates:
        markets = args.markets or list_markets()

        async def _run_explicit_dates():
            for market in markets:
                market = normalize_market(market)
                for curr_date in args.dates:
                    validate_date_string(curr_date)
                    past_date = get_past_date(91, curr_date)
                    msg = await run_crud_ops(curr_date, past_date, market=market)
                    print(msg)

        try:
            asyncio.run(_run_explicit_dates())
        except (KeyboardInterrupt, SystemExit):
            pass
    else:
        try:
            asyncio.run(cronjob(markets=args.markets))
        except (KeyboardInterrupt, SystemExit):
            pass
