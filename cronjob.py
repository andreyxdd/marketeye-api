"""
Script to set and run analytics-computing cronjobs.
The idea is to compute and insert stocks analytics every trading day (often Monday to Friday)

Raises:
    Exception: If asyncio is not imported properly use trollius
"""

import argparse
import sys
from dataclasses import dataclass, field
from typing import Optional

from time import time
from core.markets import MARKETS, list_markets, normalize_market
from core.settings import MONGO_HOT_WINDOW_DAYS
from db.crud.analytics import get_analytics_tickers
from db.crud.tracking import put_top_tickers
from db.crud.published_archive import is_session_published
from db.crud.mongo_storage import prune_mongo_session_date
from db.mongodb import connect as connect_mongo, get_database as get_mongo_database, close as close_mongo
from db.postgres import connect as connect_postgres, get_pool as get_postgres_pool, close as close_postgres
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
import scripts.mongo_storage_monitor as mongo_storage_monitor

try:
    import asyncio
except ImportError:
    import trollius as asyncio


_cron_failed = False


@dataclass
class CronPhaseError:
    market: str
    date: str
    phase: str
    error: str


@dataclass
class CronRunReport:
    errors: list[CronPhaseError] = field(default_factory=list)

    def record(self, market: str, date: str, phase: str, error: Exception | str) -> None:
        message = str(error)
        self.errors.append(
            CronPhaseError(market=market, date=date, phase=phase, error=message)
        )
        _mark_cron_failed()
        notify_developer(
            body=(
                "Analytics cronjob phase failed.\n\n"
                f"market={market}\n"
                f"date={date}\n"
                f"phase={phase}\n"
                f"error={message}"
            ),
            subject="Cronjob Report",
        )

    def has_errors(self) -> bool:
        return bool(self.errors)

    def summary_text(self) -> str:
        if not self.errors:
            return "Cron run completed with no recorded phase errors."
        lines = ["Cron run completed with errors:"]
        for item in self.errors:
            lines.append(
                f"- {item.market} {item.date} [{item.phase}]: {item.error}"
            )
        return "\n".join(lines)


def reset_cron_failed() -> None:
    global _cron_failed
    _cron_failed = False


def cron_failed() -> bool:
    return _cron_failed


def _mark_cron_failed() -> None:
    global _cron_failed
    _cron_failed = True


def _notify_cron_failure(error: Exception, curr_date: Optional[str] = None) -> None:
    epoch_suffix = get_epoch(curr_date) if curr_date else "n/a"
    notify_developer(
        body=(
            f"Analytics cronjob reported an error: {curr_date} ({epoch_suffix})"
            f" with error message:\n\n {error}"
        ),
        subject="Cronjob Report",
    )
    _mark_cron_failed()


def _format_publish_message(publish_result: dict) -> str:
    base = (
        "publish_service.publish_day:"
        f" artifacts={publish_result['artifacts_written']},"
        f" tickers={publish_result['tickers_written']}"
    )
    skipped = publish_result.get("skipped_artifacts") or []
    if skipped:
        base += f", skipped={','.join(skipped)}"
    return base


async def run_crud_ops(
    date_to_insert: str,
    date_to_remove: str,
    market: str,
    pg_pool=None,
    report: Optional[CronRunReport] = None,
) -> str:
    market = normalize_market(market)
    report = report or CronRunReport()
    msgs: list[str] = []
    ingest_ok = False

    await connect_mongo()
    conn = await get_mongo_database()
    try:
        if pg_pool is not None and await is_session_published(
            pg_pool, date_to_remove, market
        ):
            try:
                await prune_mongo_session_date(conn, date_to_remove, market)
            except Exception as prune_error:  # pylint: disable=broad-except
                report.record(market, date_to_insert, "prune", prune_error)

        try:
            msg_compute = await analytics_service.ingest_base_analytics_for_market(
                conn, date_to_insert, market=market
            )
            msgs.append(msg_compute)
            ingest_ok = True
        except Exception as ingest_error:  # pylint: disable=broad-except
            report.record(market, date_to_insert, "ingest", ingest_error)
            return "\n\n".join(msgs)

        try:
            msg_track = await put_top_tickers(conn, date_to_insert, market=market)
            msgs.append(msg_track)
        except Exception as track_error:  # pylint: disable=broad-except
            report.record(market, date_to_insert, "track", track_error)

        if not ingest_ok:
            return "\n\n".join(msgs)

        tickers_in_mongo = await get_analytics_tickers(
            conn, date_to_insert, market=market
        )
        if not tickers_in_mongo:
            msgs.append(
                "Skipping publish_service.publish_day:"
                f" no ticker analytics for {market} on {date_to_insert}"
            )
            return "\n\n".join(msgs)

        try:
            publish_result = await publish_service.publish_day(
                conn,
                pg_pool,
                date_to_insert,
                market=market,
                include_mentions=False,
            )
            for phase_error in publish_result.get("phase_errors") or []:
                report.record(market, date_to_insert, "market_analytics", phase_error)
            msgs.append(_format_publish_message(publish_result))
        except Exception as publish_error:  # pylint: disable=broad-except
            report.record(market, date_to_insert, "publish", publish_error)
            msgs.append("publish_service.publish_day failed")

        return "\n\n".join(msgs)
    finally:
        await close_mongo()


async def _finalize_cron_run(report: CronRunReport, start_time: float, market_timings: list):
    total_elapsed = round(time() - start_time, 2)
    print(f"\nAnalytics cronjob finished on {total_elapsed} seconds")
    if market_timings:
        print("Per-market summary:")
        for market, elapsed in market_timings:
            print(f"  {market}: {elapsed}s")
    print(report.summary_text())
    if report.has_errors():
        notify_developer(
            body=report.summary_text(),
            subject="Cronjob Report",
        )
    print("--------------------------------------------------------")


async def cronjob(markets=None, report: Optional[CronRunReport] = None):
    print("\n--------------------------------------------------------")
    print("Running analytics cronjob ...\n")
    start_time = time()
    report = report or CronRunReport()
    clear_ticker_universe_cache()

    markets_to_run = markets or list_markets()
    pg_pool = None
    market_timings = []

    try:
        await connect_postgres()
        pg_pool = await get_postgres_pool()
        await mongo_storage_monitor.run_monitor(manage_connections=False)
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
                report.record(market, "n/a", "session_probe", probe_error)
                continue
            finally:
                await close_mongo()

            print(f"Market {market} ({tz}) session dates: {target_dates}")

            for curr_date in target_dates:
                date_start = time()
                validate_date_string(curr_date)
                past_date = get_past_date(MONGO_HOT_WINDOW_DAYS, curr_date)
                try:
                    msg = await run_crud_ops(
                        curr_date,
                        past_date,
                        market=market,
                        pg_pool=pg_pool,
                        report=report,
                    )
                except Exception as ops_error:  # pylint: disable=broad-except
                    report.record(market, curr_date, "run_crud_ops", ops_error)
                    print(f"run_crud_ops failed for {market} {curr_date}: {ops_error}")
                else:
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
        _notify_cron_failure(e)
    finally:
        await close_postgres()

    await _finalize_cron_run(report, start_time, market_timings)


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


async def run_explicit_dates(dates, markets=None, report: Optional[CronRunReport] = None):
    markets_to_run = markets or list_markets()
    report = report or CronRunReport()
    start_time = time()

    try:
        await connect_postgres()
        pg_pool = await get_postgres_pool()
        for market in markets_to_run:
            market = normalize_market(market)
            for curr_date in dates:
                validate_date_string(curr_date)
                past_date = get_past_date(MONGO_HOT_WINDOW_DAYS, curr_date)
                try:
                    msg = await run_crud_ops(
                        curr_date,
                        past_date,
                        market=market,
                        pg_pool=pg_pool,
                        report=report,
                    )
                except Exception as ops_error:  # pylint: disable=broad-except
                    report.record(market, curr_date, "run_crud_ops", ops_error)
                    print(f"run_crud_ops failed for {market} {curr_date}: {ops_error}")
                else:
                    print(msg)
    except Exception as e:  # pylint: disable=broad-except
        print("cronjob.py: Something went wrong.")
        print("Error message:", e)
        _notify_cron_failure(e)
    finally:
        await close_postgres()

    await _finalize_cron_run(report, start_time, [])


def main():
    args = _parse_args()

    try:
        if args.dates:
            markets = args.markets or list_markets()
            asyncio.run(run_explicit_dates(args.dates, markets=markets))
        else:
            asyncio.run(cronjob(markets=args.markets))
    except (KeyboardInterrupt, SystemExit):
        raise

    if cron_failed():
        sys.exit(1)


if __name__ == "__main__":
    main()
