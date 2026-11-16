#!/usr/bin/env python3
"""One-shot band-frequency backfill for Micro screening.

For each published session in a lookback window, upserts band + unbanded
Mongo tracking via ``put_top_tickers``, then patches ``frequencies`` on
existing published list artifacts (no hot enrich / external API calls).

Use ``--full-publish`` to restore the old ``publish_day`` path (slow).

Required env:
  MONGO_URI       Mongo connection string
  DATABASE_URL    PostgreSQL DSN for the published archive

Optional env:
  MONGO_DB_NAME   Mongo database name (defaults from settings)

Examples:
  python scripts/backfill_band_tracking.py --markets US,TO --trading-days 15 --dry-run
  python scripts/backfill_band_tracking.py --markets US,TO --trading-days 15
  python scripts/backfill_band_tracking.py --markets US --trading-days 15 --full-publish
  python scripts/backfill_band_tracking.py --markets TO --trading-days 40 --reingest-missing
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.markets import market_mongo_filter, normalize_market
from core.settings import MONGO_DB_NAME
from db.crud.published_archive import (
    build_criterion_artifact_key,
    build_lists_artifact_key,
    get_artifact_payload,
    get_published_dates,
    upsert_artifact,
)
from db.crud.tracking import CRITERIA, get_analytics_frequencies, put_top_tickers
from db.mongodb import close as close_mongo
from db.mongodb import connect as connect_mongo
from db.mongodb import get_database as get_mongo_database
from db.postgres import close as close_postgres
from db.postgres import connect as connect_postgres
from db.postgres import get_pool as get_postgres_pool
from services.analytics_service import ingest_base_analytics_for_market
from services.publish_service import PRICE_BANDS_TO_PUBLISH, publish_day
from utils.handle_datetimes import get_epoch


def _criterion_payload_key(criterion: str) -> str:
    return f"by_{criterion}"


def parse_markets(raw: str) -> list[str]:
    markets = [normalize_market(part.strip()) for part in raw.split(",") if part.strip()]
    if not markets:
        raise ValueError("at least one market required")
    return markets


def select_trading_days(date_rows: Sequence[dict], trading_days: int) -> list[str]:
    """Take the N most recent published session dates (already trading days)."""
    strings = [row["date_string"] for row in date_rows]
    if trading_days <= 0:
        return []
    return strings[-trading_days:]


async def analytics_exist(conn, date: str, market: str) -> bool:
    epoch_date = get_epoch(date)
    query = {"date": epoch_date, **market_mongo_filter(market)}
    count = await conn[MONGO_DB_NAME]["analytics"].count_documents(query)
    return count > 0


async def _patch_rows_frequencies(
    conn,
    date: str,
    criterion: str,
    rows: list,
    market: str,
    price_band: Optional[str],
    freq_cache: dict[tuple[str, Optional[str], str], str],
) -> None:
    for row in rows:
        ticker = row.get("ticker")
        if not ticker:
            continue
        cache_key = (criterion, price_band, ticker)
        if cache_key not in freq_cache:
            freq_cache[cache_key] = await get_analytics_frequencies(
                conn,
                date,
                criterion,
                ticker,
                market=market,
                price_band=price_band,
            )
        row["frequencies"] = freq_cache[cache_key]


async def patch_day_frequencies(conn, pool, date: str, market: str = "US") -> int:
    """Patch frequencies on existing published list/criterion artifacts.

    Skips missing artifacts (no hot rebuild). Returns count of artifacts upserted.
    """
    market = normalize_market(market)
    written = 0
    freq_cache: dict[tuple[str, Optional[str], str], str] = {}

    for price_band in PRICE_BANDS_TO_PUBLISH:
        lists_key = build_lists_artifact_key(price_band)
        lists_payload = await get_artifact_payload(
            pool, date, lists_key, market=market
        )
        if lists_payload is None:
            print(f"  skip {market} {date}: missing artifact {lists_key}")
        else:
            for criterion in CRITERIA:
                rows = lists_payload.get(_criterion_payload_key(criterion)) or []
                if not isinstance(rows, list):
                    continue
                await _patch_rows_frequencies(
                    conn, date, criterion, rows, market, price_band, freq_cache
                )
            await upsert_artifact(
                pool, date, lists_key, lists_payload, market=market
            )
            written += 1

        for criterion in CRITERIA:
            crit_key = build_criterion_artifact_key(criterion, price_band)
            crit_payload = await get_artifact_payload(
                pool, date, crit_key, market=market
            )
            if crit_payload is None:
                print(f"  skip {market} {date}: missing artifact {crit_key}")
                continue
            rows = crit_payload.get(criterion) or []
            if isinstance(rows, list):
                await _patch_rows_frequencies(
                    conn, date, criterion, rows, market, price_band, freq_cache
                )
            await upsert_artifact(
                pool, date, crit_key, crit_payload, market=market
            )
            written += 1

    return written


async def backfill_market(
    conn,
    pool,
    market: str,
    trading_days: int,
    dry_run: bool,
    full_publish: bool = False,
    reingest_missing: bool = False,
) -> int:
    """Apply or dry-run one market. Returns count of failed apply dates."""
    market = normalize_market(market)
    date_rows = await get_published_dates(pool, market=market)
    dates = select_trading_days(date_rows, trading_days)
    print(f"{market}: {len(dates)} session(s) in window (trading-days={trading_days})")
    failures = 0

    for date in dates:
        has_analytics = await analytics_exist(conn, date, market)
        needs_ingest = not has_analytics
        if needs_ingest and not reingest_missing:
            print(f"  skip {market} {date}: no Mongo analytics")
            continue

        if dry_run:
            action = "publish_day" if full_publish else "patch frequencies"
            if needs_ingest:
                print(
                    f"  dry-run {market} {date}: would ingest analytics then "
                    f"put_top_tickers then {action}"
                )
            else:
                print(
                    f"  dry-run {market} {date}: would put_top_tickers then {action}"
                )
            continue

        if needs_ingest:
            # One-shot ops recovery only — not wired into daily cron auto-repair.
            print(f"  apply {market} {date}: ingest analytics")
            await ingest_base_analytics_for_market(conn, date, market=market)
            if not await analytics_exist(conn, date, market):
                print(
                    f"  fail {market} {date}: analytics still missing after ingest; "
                    "skipping put_top_tickers and frequency patch"
                )
                failures += 1
                continue

        print(f"  apply {market} {date}: put_top_tickers")
        await put_top_tickers(conn, date, market=market)

        if full_publish:
            print(f"  apply {market} {date}: publish_day")
            await publish_day(
                conn, pool, date, market=market, include_mentions=False
            )
        else:
            print(f"  apply {market} {date}: patch frequencies")
            written = await patch_day_frequencies(conn, pool, date, market=market)
            print(f"  apply {market} {date}: patched {written} artifact(s)")

    return failures


async def run_backfill(
    markets: Iterable[str],
    trading_days: int,
    dry_run: bool,
    full_publish: bool = False,
    reingest_missing: bool = False,
) -> int:
    """Returns total failed apply dates across markets (0 on dry-run / success)."""
    await connect_mongo()
    await connect_postgres()
    failures = 0
    try:
        conn = await get_mongo_database()
        pool = await get_postgres_pool()
        for market in markets:
            failures += await backfill_market(
                conn,
                pool,
                market,
                trading_days=trading_days,
                dry_run=dry_run,
                full_publish=full_publish,
                reingest_missing=reingest_missing,
            )
    finally:
        await close_mongo()
        await close_postgres()
    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill band + unbanded tracking for recent published sessions, "
            "then patch frequencies on existing published artifacts (default). "
            "Use --full-publish to republish via publish_day (hits external APIs)."
        ),
        epilog=(
            "Required env: MONGO_URI, DATABASE_URL. "
            "Optional: MONGO_DB_NAME. "
            "Default path patches frequencies only; --full-publish restores slow republish."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--markets",
        default="US,TO",
        help="Comma-separated markets (default: US,TO)",
    )
    parser.add_argument(
        "--trading-days",
        type=int,
        default=15,
        help="Number of most recent published sessions per market (default: 15)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan without writing tracking or publishing",
    )
    parser.add_argument(
        "--full-publish",
        action="store_true",
        help="Call publish_day (hot enrich) instead of frequency patch (default: off)",
    )
    parser.add_argument(
        "--reingest-missing",
        action="store_true",
        help=(
            "For dates missing Mongo analytics, ingest then track+patch "
            "(default: skip those dates)"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    markets = parse_markets(args.markets)
    failures = asyncio.run(
        run_backfill(
            markets=markets,
            trading_days=args.trading_days,
            dry_run=args.dry_run,
            full_publish=args.full_publish,
            reingest_missing=args.reingest_missing,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
