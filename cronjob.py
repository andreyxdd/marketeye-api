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
import asyncpg
from core.markets import MARKETS, list_markets, normalize_market
from core.settings import DATABASE_URL, MONGO_HOT_WINDOW_DAYS
from db.crud.analytics import get_analytics_tickers
from db.crud.tracking import (
    count_prior_unbanded_tracking_sessions,
    put_top_tickers,
)

# Alert when TO prior unbanded tracking sessions in the frequencies window
# fall below this floor (alert/fail only — no auto-backfill).
TO_TRACKING_DENSITY_FLOOR = 10
TO_TRACKING_DENSITY_PERIOD = 25
from db.crud.published_archive import is_archive_complete
from db.crud.mongo_storage import prune_mongo_session_date
from db.mongodb import (
    connect as connect_mongo,
    get_database as get_mongo_database,
    close as close_mongo,
)
from db.postgres import (
    connect as connect_postgres,
    get_pool as get_postgres_pool,
    close as close_postgres,
    normalize_database_url,
)
from utils.handle_telegram import notify_developer
from utils.handle_datetimes import (
    get_past_date,
    get_epoch,
)
from utils.handle_validation import validate_date_string
from utils.handle_external_apis import clear_ticker_universe_cache
import services.analytics_service as analytics_service
import services.publish_service as publish_service
from services.cron_dates import unpublished_session_dates
import scripts.mongo_storage_monitor as mongo_storage_monitor

try:
    import asyncio
except ImportError:
    import trollius as asyncio


_cron_failed = False

_PUBLISH_RETRY_ERRORS = (
    asyncpg.PostgresConnectionError,
    asyncpg.InterfaceError,
    OSError,
    asyncio.TimeoutError,
)


@dataclass
class CronPhaseError:
    market: str
    date: str
    phase: str
    error: str


@dataclass
class CronPhaseTiming:
    market: str
    date: str
    phase: str
    elapsed_seconds: float


@dataclass
class CronRunReport:
    errors: list[CronPhaseError] = field(default_factory=list)
    timings: list[CronPhaseTiming] = field(default_factory=list)

    def record(
        self, market: str, date: str, phase: str, error: Exception | str
    ) -> None:
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

    def record_timing(
        self, market: str, date: str, phase: str, elapsed_seconds: float
    ) -> None:
        self.timings.append(
            CronPhaseTiming(
                market=market,
                date=date,
                phase=phase,
                elapsed_seconds=elapsed_seconds,
            )
        )

    def has_errors(self) -> bool:
        return bool(self.errors)

    def summary_text(self) -> str:
        if self.errors:
            lines = ["Cron run completed with errors:"]
            for item in self.errors:
                lines.append(
                    f"- {item.market} {item.date} [{item.phase}]: {item.error}"
                )
        else:
            lines = ["Cron run completed with no recorded phase errors."]
        if self.timings:
            lines.append("Phase timings (seconds):")
            for item in self.timings:
                lines.append(
                    f"- {item.market} {item.date} [{item.phase}]: "
                    f"{item.elapsed_seconds}s"
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


async def _publish_day_with_retry(
    conn, pg_pool, date_to_insert: str, market: str
) -> dict:
    try:
        return await publish_service.publish_day(
            conn, pg_pool, date_to_insert, market=market, include_mentions=False
        )
    except _PUBLISH_RETRY_ERRORS:
        return await publish_service.publish_day(
            conn, pg_pool, date_to_insert, market=market, include_mentions=False
        )


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
        if pg_pool is not None and await is_archive_complete(
            pg_pool, date_to_remove, market
        ):
            phase_start = time()
            try:
                await prune_mongo_session_date(
                    conn, date_to_remove, market, pool=pg_pool
                )
            except Exception as prune_error:  # pylint: disable=broad-except
                report.record(market, date_to_insert, "prune", prune_error)
            finally:
                report.record_timing(
                    market,
                    date_to_insert,
                    "prune",
                    round(time() - phase_start, 2),
                )

        phase_start = time()
        try:
            msg_compute = await analytics_service.ingest_base_analytics_for_market(
                conn, date_to_insert, market=market
            )
            msgs.append(msg_compute)
            ingest_ok = True
        except Exception as ingest_error:  # pylint: disable=broad-except
            report.record(market, date_to_insert, "ingest", ingest_error)
            return "\n\n".join(msgs)
        finally:
            report.record_timing(
                market,
                date_to_insert,
                "ingest",
                round(time() - phase_start, 2),
            )

        # TO only: skip publish when frequencies lookback is too shallow
        # (ceiling: skip publish only — no auto-backfill).
        skip_publish_for_density = False
        phase_start = time()
        try:
            msg_track = await put_top_tickers(conn, date_to_insert, market=market)
            msgs.append(msg_track)
        except Exception as track_error:  # pylint: disable=broad-except
            report.record(market, date_to_insert, "track", track_error)
        else:
            if market == "TO":
                try:
                    prior = await count_prior_unbanded_tracking_sessions(
                        conn,
                        date_to_insert,
                        period=TO_TRACKING_DENSITY_PERIOD,
                        market=market,
                    )
                    if prior < TO_TRACKING_DENSITY_FLOOR:
                        report.record(
                            market,
                            date_to_insert,
                            "track_density",
                            (
                                f"TO prior unbanded tracking sessions={prior} "
                                f"below floor={TO_TRACKING_DENSITY_FLOOR} "
                                f"(period={TO_TRACKING_DENSITY_PERIOD}); "
                                "frequencies history is too shallow"
                            ),
                        )
                        skip_publish_for_density = True
                except Exception as density_error:  # pylint: disable=broad-except
                    report.record(
                        market, date_to_insert, "track_density", density_error
                    )
                    skip_publish_for_density = True
        finally:
            report.record_timing(
                market,
                date_to_insert,
                "track",
                round(time() - phase_start, 2),
            )

        if not ingest_ok:
            return "\n\n".join(msgs)

        if skip_publish_for_density:
            msgs.append(
                "Skipping publish_service.publish_day:"
                f" TO tracking density below floor on {date_to_insert}"
            )
            return "\n\n".join(msgs)

        tickers_in_mongo = await get_analytics_tickers(
            conn, date_to_insert, market=market
        )
        if not tickers_in_mongo and market != "US":
            msgs.append(
                "Skipping publish_service.publish_day:"
                f" no ticker analytics for {market} on {date_to_insert}"
            )
            return "\n\n".join(msgs)

        phase_start = time()
        try:
            publish_result = await _publish_day_with_retry(
                conn, pg_pool, date_to_insert, market
            )
            for phase_error in publish_result.get("phase_errors") or []:
                phase = (
                    "stock_bounce_v2"
                    if phase_error.startswith(
                        ("stock_bounce:v2:", "stock_bounce:v2-seed:")
                    )
                    else "stock_bounce"
                    if phase_error.startswith("stock_bounce:")
                    else "market_analytics"
                )
                report.record(market, date_to_insert, phase, phase_error)
            msgs.append(_format_publish_message(publish_result))
        except Exception as publish_error:  # pylint: disable=broad-except
            report.record(market, date_to_insert, "publish", publish_error)
            msgs.append("publish_service.publish_day failed")
        finally:
            report.record_timing(
                market,
                date_to_insert,
                "publish",
                round(time() - phase_start, 2),
            )

        return "\n\n".join(msgs)
    finally:
        await close_mongo()


async def _finalize_cron_run(
    report: CronRunReport, start_time: float, market_timings: list
):
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
        try:
            await mongo_storage_monitor.run_monitor(manage_connections=False)
        except Exception as monitor_error:  # pylint: disable=broad-except
            print(f"cronjob.py: mongo storage monitor failed: {monitor_error}")
            report.record("n/a", "n/a", "mongo_monitor", monitor_error)
        else:
            for market in markets_to_run:
                market_start = time()
                market = normalize_market(market)
                tz = MARKETS[market]["timezone"]

                try:
                    target_dates = await unpublished_session_dates(pg_pool, market)
                except Exception as probe_error:  # pylint: disable=broad-except
                    print(
                        f"cronjob.py: session probe failed for {market} ({tz}): {probe_error}"
                    )
                    report.record(market, "n/a", "session_probe", probe_error)
                    continue

                print(f"Market {market} ({tz}) session dates: {target_dates}")
                if not target_dates:
                    print(
                        f"Market {market}: all latest sessions already published; skipping"
                    )
                    continue

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
                        print(
                            f"run_crud_ops failed for {market} {curr_date}: {ops_error}"
                        )
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


async def run_explicit_dates(
    dates, markets=None, report: Optional[CronRunReport] = None
):
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


# Fixed key for pg_try_advisory_lock: one cron run at a time (clock dyno, GHA, manual).
CRON_LOCK_KEY = 74_032_601


async def acquire_run_lock():
    """Return a dedicated connection holding the cron lock, or None if another run holds it.

    Postgres drops the lock when this connection closes or the process dies.
    """
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    # Server-side TCP keepalives: this connection sits idle for the whole run, and an idle flow
    # dropped by the network would release the lock early. Count x interval tolerates a ~5 min
    # blip before Postgres gives up on the connection (and the lock).
    conn = await asyncpg.connect(
        normalize_database_url(DATABASE_URL),
        server_settings={
            "tcp_keepalives_idle": "60",
            "tcp_keepalives_interval": "30",
            "tcp_keepalives_count": "10",
        },
    )
    if await conn.fetchval("SELECT pg_try_advisory_lock($1)", CRON_LOCK_KEY):
        return conn
    await conn.close()
    return None


async def _run_locked(args):
    try:
        lock_conn = await acquire_run_lock()
    except Exception as e:  # pylint: disable=broad-except
        print("cronjob.py: could not acquire run lock.")
        print("Error message:", e)
        _notify_cron_failure(e)
        return
    if lock_conn is None:
        print("cron busy: another run holds the lock", flush=True)
        return
    try:
        if args.dates:
            markets = args.markets or list_markets()
            await run_explicit_dates(args.dates, markets=markets)
        else:
            await cronjob(markets=args.markets)
    finally:
        await lock_conn.close()


def main():
    args = _parse_args()

    try:
        asyncio.run(_run_locked(args))
    except (KeyboardInterrupt, SystemExit):
        raise

    if cron_failed():
        sys.exit(1)


if __name__ == "__main__":
    main()
