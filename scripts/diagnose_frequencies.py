#!/usr/bin/env python3
"""Diagnose even-only Frequencies (T-2, T-4, … missing T-1).

Classifies whether the pattern is tracking dupes / enum bug
(``dupes_or_enum``) or intended ``$lt`` semantics that exclude the
current session (``semantics_only``).

Required env: MONGO_URI (or MONGO_USERNAME/PASSWORD/DB_NAME via settings).

Examples:
  python scripts/diagnose_frequencies.py --market US --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from core.markets import market_mongo_filter, normalize_market
from core.settings import MONGO_DB_NAME
from db.crud.tracking import (
    CRITERIA,
    MONGO_TRACKING_COLLECTION,
    _merge_filters,
    get_analytics_frequencies,
)
from db.mongodb import close as close_mongo
from db.mongodb import connect as connect_mongo
from db.mongodb import get_database as get_mongo_database
from utils.handle_datetimes import get_date_string, get_epoch, get_past_date

_T_N_RE = re.compile(r"T-(\d+)")


def frequencies_from_membership(membership: Sequence[bool]) -> str:
    """Build ``T-N`` string from prior-session membership (index 0 = T-1)."""
    parts = [f"T-{idx + 1}" for idx, present in enumerate(membership) if present]
    return ", ".join(parts)


def parse_t_ns(frequencies: str) -> list[int]:
    return [int(m.group(1)) for m in _T_N_RE.finditer(frequencies or "")]


def is_even_only(frequencies: str) -> bool:
    """True when string has T-2, no odd T-N, and lacks T-1 (even-only pattern)."""
    nums = parse_t_ns(frequencies)
    if not nums:
        return False
    has_odd = any(n % 2 == 1 for n in nums)
    return (2 in nums) and not has_odd


def _band_key(price_band: Any) -> Optional[str]:
    return None if price_band is None else str(price_band)


def _band_filter(price_band: Optional[str]) -> dict:
    if price_band is not None:
        return {"price_band": price_band}
    return {
        "$or": [
            {"price_band": None},
            {"price_band": {"$exists": False}},
        ]
    }


async def fetch_prior_tracking(
    conn,
    date: str,
    criterion: str,
    market: str,
    price_band: Optional[str],
    period: int = 25,
) -> list[dict]:
    """Same window as ``get_analytics_frequencies``: $gt past, $lt current."""
    market = normalize_market(market)
    epoch_past = get_epoch(get_past_date(period, date))
    epoch_date = get_epoch(date)
    pipeline = [
        {
            "$match": {
                "criterion": criterion,
                **_merge_filters(market_mongo_filter(market), _band_filter(price_band)),
            }
        },
        {"$match": {"date": {"$gt": epoch_past, "$lt": epoch_date}}},
        {"$sort": {"date": -1}},
    ]
    cursor = conn[MONGO_DB_NAME][MONGO_TRACKING_COLLECTION].aggregate(pipeline)
    return await cursor.to_list(length=period)


async def ticker_on_session(
    conn,
    date: str,
    criterion: str,
    ticker: str,
    market: str,
    price_band: Optional[str],
) -> bool:
    """Whether ticker is in tracking for the session date (inclusive)."""
    market = normalize_market(market)
    epoch_date = get_epoch(date)
    query = {
        "date": epoch_date,
        "criterion": criterion,
        **_merge_filters(market_mongo_filter(market), _band_filter(price_band)),
    }
    docs = (
        await conn[MONGO_DB_NAME][MONGO_TRACKING_COLLECTION]
        .find(query, {"tickers": True})
        .to_list(length=20)
    )
    return any(ticker in (doc.get("tickers") or []) for doc in docs)


async def audit_tracking_density(
    conn,
    market: str,
    dates: Sequence[str],
    criteria: Sequence[str] | None = None,
) -> tuple[int, list[tuple[tuple, int]]]:
    """Count tracking docs per (date, criterion, market, price_band)."""
    market = normalize_market(market)
    criteria = list(criteria or CRITERIA)
    epochs = [get_epoch(d) for d in dates]
    query = {
        "date": {"$in": epochs},
        "criterion": {"$in": criteria},
        **market_mongo_filter(market),
    }
    cursor = conn[MONGO_DB_NAME][MONGO_TRACKING_COLLECTION].find(
        query,
        {"date": True, "criterion": True, "market": True, "price_band": True},
    )
    docs = await cursor.to_list(length=50_000)
    counts: Counter[tuple] = Counter()
    for doc in docs:
        key = (
            get_date_string(doc["date"]),
            doc.get("criterion"),
            doc.get("market", market),
            _band_key(doc.get("price_band")),
        )
        counts[key] += 1
    def _sort_key(item: tuple[tuple, int]) -> tuple:
        (d, crit, mkt, band), _n = item
        return (d or "", crit or "", mkt or "", band or "")

    dupes = [(k, n) for k, n in sorted(counts.items(), key=_sort_key) if n > 1]
    return len(dupes), dupes


async def recent_tracking_dates(conn, market: str, limit: int = 40) -> list[str]:
    market = normalize_market(market)
    pipeline = [
        {"$match": market_mongo_filter(market)},
        {"$group": {"_id": "$date"}},
        {"$sort": {"_id": -1}},
        {"$limit": limit},
    ]
    cursor = conn[MONGO_DB_NAME][MONGO_TRACKING_COLLECTION].aggregate(pipeline)
    rows = await cursor.to_list(length=limit)
    return [get_date_string(row["_id"]) for row in rows]


async def find_even_only_samples(
    conn,
    market: str,
    limit: int,
    lookback_dates: int = 30,
) -> list[dict]:
    """Scan recent sessions for even-only frequency strings."""
    market = normalize_market(market)
    dates = await recent_tracking_dates(conn, market, limit=lookback_dates)
    samples: list[dict] = []
    seen: set[tuple] = set()

    for date in dates:
        if len(samples) >= limit:
            break
        epoch = get_epoch(date)
        for criterion in CRITERIA:
            if len(samples) >= limit:
                break
            # Prefer unbanded + first band that yields tickers.
            for price_band in (None, "lte5", "gt5_lte10", "gt10_lte20", "gt20"):
                if len(samples) >= limit:
                    break
                query = {
                    "date": epoch,
                    "criterion": criterion,
                    **_merge_filters(
                        market_mongo_filter(market), _band_filter(price_band)
                    ),
                }
                docs = (
                    await conn[MONGO_DB_NAME][MONGO_TRACKING_COLLECTION]
                    .find(query, {"tickers": True, "price_band": True})
                    .to_list(length=5)
                )
                tickers: list[str] = []
                for doc in docs:
                    tickers.extend(doc.get("tickers") or [])
                # Also probe prior-session members via frequencies on a few tickers
                # from adjacent docs if today empty.
                candidates = list(dict.fromkeys(tickers))[:15]
                if not candidates:
                    prior = await fetch_prior_tracking(
                        conn, date, criterion, market, price_band, period=5
                    )
                    for doc in prior[:3]:
                        candidates.extend((doc.get("tickers") or [])[:5])
                    candidates = list(dict.fromkeys(candidates))[:15]

                for ticker in candidates:
                    if len(samples) >= limit:
                        break
                    key = (date, criterion, ticker, price_band)
                    if key in seen:
                        continue
                    seen.add(key)
                    freq = await get_analytics_frequencies(
                        conn,
                        date,
                        criterion,
                        ticker,
                        market=market,
                        price_band=price_band,
                    )
                    if not is_even_only(freq):
                        continue
                    prior_docs = await fetch_prior_tracking(
                        conn, date, criterion, market, price_band
                    )
                    membership = [
                        ticker in (doc.get("tickers") or []) for doc in prior_docs
                    ]
                    expected = frequencies_from_membership(membership)
                    on_current = await ticker_on_session(
                        conn, date, criterion, ticker, market, price_band
                    )
                    samples.append(
                        {
                            "date": date,
                            "criterion": criterion,
                            "ticker": ticker,
                            "market": market,
                            "price_band": price_band,
                            "frequencies": freq,
                            "expected": expected,
                            "membership": membership,
                            "on_current": on_current,
                            "prior_dates": [
                                get_date_string(d["date"]) for d in prior_docs
                            ],
                        }
                    )
    return samples


def classify_sample(
    sample: dict,
    dupe_count: int,
) -> tuple[str, str]:
    """Return (classification, notes). Prefer dupes_or_enum when dupes>0."""
    membership: list[bool] = sample["membership"]
    actual = sample["frequencies"] or ""
    expected = sample["expected"] or ""
    odd_present = any(
        present and ((idx + 1) % 2 == 1) for idx, present in enumerate(membership)
    )
    odd_in_string = any(n % 2 == 1 for n in parse_t_ns(actual))
    expected_eq_actual = expected == actual

    if dupe_count > 0:
        return (
            "dupes_or_enum",
            f"dupes={dupe_count}; expected==actual={expected_eq_actual}",
        )

    if odd_present and not odd_in_string:
        return (
            "dupes_or_enum",
            "odd membership True but string skips odd T-N",
        )

    if not expected_eq_actual:
        return (
            "dupes_or_enum",
            f"expected!=actual ({expected!r} vs {actual!r})",
        )

    if not odd_present and sample.get("on_current") and 1 not in parse_t_ns(actual):
        # Current-day presence excluded by $lt → missing T-1 is semantics.
        return (
            "semantics_only",
            "no dupes; odd indices empty; on_current=True excluded by $lt",
        )

    if not odd_present:
        return (
            "semantics_only",
            "no dupes; odd indices empty; even-only matches membership",
        )

    return (
        "semantics_only",
        "ambiguous without dupes; default semantics_only",
    )


async def run(market: str, limit: int) -> int:
    market = normalize_market(market)
    await connect_mongo()
    try:
        conn = await get_mongo_database()
        print(f"=== sample even-only (market={market}, limit={limit}) ===")
        samples = await find_even_only_samples(conn, market, limit=limit)
        if not samples:
            print("sample: none found")
            print("dupes=0")
            print("classification=unknown")
            print("notes: no even-only rows in lookback; cannot classify")
            return 0

        for i, s in enumerate(samples, 1):
            print(
                f"sample[{i}]: date={s['date']} criterion={s['criterion']} "
                f"ticker={s['ticker']} market={s['market']} "
                f"price_band={s['price_band']!r} frequencies={s['frequencies']!r}"
            )

        # Audit window: union of sample dates + their prior session dates.
        window_dates: set[str] = set()
        for s in samples:
            window_dates.add(s["date"])
            window_dates.update(s.get("prior_dates") or [])
        print(f"=== audit tracking density (dates={len(window_dates)}) ===")
        dupe_count, dupes = await audit_tracking_density(
            conn, market, sorted(window_dates)
        )
        if dupe_count == 0:
            print("dupes=0")
        else:
            print(f"dupes={dupe_count}")
            for key, n in dupes[:20]:
                print(f"DUPE count={n} key={key}")

        primary = samples[0]
        print("=== falsify membership vs labels ===")
        print(f"ticker={primary['ticker']} date={primary['date']}")
        print(f"membership={primary['membership'][:15]}...")
        print(f"expected={primary['expected']!r}")
        print(f"actual={primary['frequencies']!r}")
        print(f"on_current={primary['on_current']}")
        classification, notes = classify_sample(primary, dupe_count)
        print(f"classification={classification}")
        print(f"notes={notes}")
        return 0
    finally:
        await close_mongo()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnose even-only Frequencies vs tracking dupes / $lt semantics",
    )
    parser.add_argument("--market", default="US", help="Market code (default: US)")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max even-only sample rows to print (default: 5)",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Kept for CLI compatibility; audit always runs after sample",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run(args.market, args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
