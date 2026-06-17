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
from db.postgres import connect as connect_postgres, get_pool as get_postgres_pool, close as close_postgres
from db.crud.analytics import remove_base_analytics
from db.crud.scrapes import remove_scrapes
from utils.handle_telegram import notify_developer
from utils.handle_datetimes import (
    get_past_date,
    get_epoch,
)
from utils.handle_validation import validate_date_string
from utils.handle_external_apis import clear_ticker_universe_cache
import services.analytics_service as analytics_service
import services.publish_service as publish_service
from services.cron_dates import resolve_ingest_dates_for_market

try:
    import asyncio
except ImportError:
    import trollius as asyncio


async def run_crud_ops(date_to_insert: str, date_to_remove: str, market: str, pg_pool=None) -> str:
    await connect_mongo()
    conn = await get_mongo_database()
    try:
        msg_compute = await analytics_service.ingest_base_analytics_for_market(
            conn, date_to_insert, market=market
        )
        msg_track = await put_top_tickers(conn, date_to_insert, market=market)

        try:
            publish_result = await publish_service.publish_day(
                conn, pg_pool, date_to_insert, market=market
            )
        except Exception as publish_error:  # pylint: disable=broad-except
            notify_developer(
                body=(
                    "Analytics cronjob publish gate failed; skipped Mongo prune.\n\n"
                    f"market={market}\n"
                    f"date_to_insert={date_to_insert}\n"
                    f"date_to_remove={date_to_remove}\n"
                    f"error={publish_error}"
                ),
                subject="Cronjob Report",
            )
            return (
                msg_compute
                + "\n\n"
                + msg_track
                + "\n\n"
                + "publish_service.publish_day failed; skipped remove_base_analytics"
            )

        await remove_base_analytics(conn, date_to_remove, market=market)
        await remove_base_analytics(conn, date_to_remove, "tracking", market=market)
        if market == "US":
            await remove_scrapes(conn, date_to_remove)

        return (
            msg_compute
            + "\n\n"
            + msg_track
            + "\n\n"
            + (
                "publish_service.publish_day:"
                f" artifacts={publish_result['artifacts_written']},"
                f" tickers={publish_result['tickers_written']}"
            )
        )
    finally:
        await close_mongo()


async def cronjob(markets=None):
    print("\n--------------------------------------------------------")
    print("Running analytics cronjob ...\n")
    start_time = time()
    clear_ticker_universe_cache()

    markets_to_run = markets or list_markets()
    curr_date = None
    pg_pool = None

    market_timings = []

    try:
        await connect_postgres()
        pg_pool = await get_postgres_pool()
        for market in markets_to_run:
            market_start = time()
            market = normalize_market(market)
            tz = MARKETS[market]["timezone"]

            await connect_mongo()
            conn = await get_mongo_database()
            try:
                target_dates = await resolve_ingest_dates_for_market(conn, market)
            except Exception as probe_error:  # pylint: disable=broad-except
                print(
                    f"cronjob.py: session probe failed for {market} ({tz}): {probe_error}"
                )
                notify_developer(
                    body=(
                        f"Analytics cronjob session probe failed for {market} ({tz})"
                        f" with error message:\n\n {probe_error}"
                    ),
                    subject="Cronjob Report",
                )
                continue
            finally:
                await close_mongo()

            print(f"Market {market} ({tz}) session dates: {target_dates}")

            for curr_date in target_dates:
                date_start = time()
                validate_date_string(curr_date)
                past_date = get_past_date(91, curr_date)
                msg = await run_crud_ops(curr_date, past_date, market=market, pg_pool=pg_pool)
                print(msg)
                print(
                    f"Market {market} date {curr_date} finished in "
                    f"{round(time() - date_start, 2)} seconds"
                )

            market_elapsed = round(time() - market_start, 2)
            market_timings.append((market, market_elapsed))
            print(f"Market {market} total: {market_elapsed} seconds")

    except Exception as e:  # pylint: disable=W0703
        print("cronjob.py: Something went wrong.")
        print("Error message:", e)
        notify_developer(
            body=f"Analytics cronjob reported an error: {curr_date} ({get_epoch(curr_date) if curr_date else 'n/a'})"
            + f" with error message:\n\n {e}",
            subject="Cronjob Report",
        )
    finally:
        await close_postgres()

    total_elapsed = round(time() - start_time, 2)
    print(f"\nAnalytics cronjob finished on {total_elapsed} seconds")
    if market_timings:
        print("Per-market summary:")
        for market, elapsed in market_timings:
            print(f"  {market}: {elapsed}s")
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
            await connect_postgres()
            try:
                pg_pool = await get_postgres_pool()
                for market in markets:
                    market = normalize_market(market)
                    for curr_date in args.dates:
                        validate_date_string(curr_date)
                        past_date = get_past_date(91, curr_date)
                        msg = await run_crud_ops(
                            curr_date,
                            past_date,
                            market=market,
                            pg_pool=pg_pool,
                        )
                        print(msg)
            finally:
                await close_postgres()

        try:
            asyncio.run(_run_explicit_dates())
        except (KeyboardInterrupt, SystemExit):
            pass
    else:
        try:
            asyncio.run(cronjob(markets=args.markets))
        except (KeyboardInterrupt, SystemExit):
            pass
