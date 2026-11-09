"""Pure StockBounce v2 snapshot validation and combined screening."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Iterable


UNIVERSES = ("whole_market", "macd_history")
MAX_LOOKBACK = 1260
MAX_ROWS = 20


class UnsupportedLookbackError(ValueError):
    """A syntactically valid lookback exceeds the session's retained coverage."""

    def __init__(self, lookback: int, max_lookback: int):
        super().__init__(
            f"lookback {lookback} exceeds supported coverage {max_lookback}"
        )
        self.lookback = lookback
        self.max_lookback = max_lookback


def _date_value(value) -> str:
    if isinstance(value, str):
        return value[:10]
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    raise ValueError("bar date is invalid")


def _finite_number(value) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def validate_snapshot_v2(snapshot: dict) -> None:
    if not isinstance(snapshot, dict):
        raise ValueError("StockBounce v2 snapshot must be an object")
    if snapshot.get("schema_version") != 2 or snapshot.get("market") != "US":
        raise ValueError("Unsupported StockBounce v2 snapshot")
    try:
        parsed = datetime.strptime(snapshot["date"], "%Y-%m-%d").date()
        if parsed.isoformat() != snapshot["date"]:
            raise ValueError("non-canonical date")
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "StockBounce v2 snapshot has an invalid session date"
        ) from error
    max_lookback = snapshot.get("max_lookback")
    if (
        isinstance(max_lookback, bool)
        or not isinstance(max_lookback, int)
        or not 0 <= max_lookback <= MAX_LOOKBACK
    ):
        raise ValueError("StockBounce v2 snapshot max_lookback is invalid")
    rows = snapshot.get("rows")
    coverage = snapshot.get("coverage")
    if not isinstance(rows, list) or not isinstance(coverage, dict):
        raise ValueError("StockBounce v2 snapshot requires rows and coverage")
    tickers = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("ticker"), str):
            raise ValueError("StockBounce v2 rows require ticker symbols")
        ticker = row["ticker"]
        if not ticker or ticker in tickers:
            raise ValueError("StockBounce v2 snapshot contains duplicate tickers")
        tickers.add(ticker)
        if any(
            not _finite_number(row.get(field))
            for field in ("open", "high", "close", "volume", "previous_all_time_high")
        ):
            raise ValueError(f"StockBounce v2 row {ticker} has invalid numeric fields")
        if row["open"] <= 0 or row["previous_all_time_high"] < 0:
            raise ValueError(f"StockBounce v2 row {ticker} has invalid price evidence")
        membership = row.get("universes")
        if (
            not isinstance(membership, list)
            or not membership
            or len(set(membership)) != len(membership)
            or any(universe not in UNIVERSES for universe in membership)
        ):
            raise ValueError(f"StockBounce v2 row {ticker} has invalid membership")
    for universe in UNIVERSES:
        item = coverage.get(universe)
        if not isinstance(item, dict) or item.get("status") not in (
            "exact",
            "degraded",
        ):
            raise ValueError("StockBounce v2 snapshot has incomplete coverage")
        if (
            not isinstance(item.get("universe_provenance"), str)
            or not item["universe_provenance"]
        ):
            raise ValueError("StockBounce v2 coverage requires provenance")
        exclusions_count = item.get("exclusions_count")
        if (
            isinstance(exclusions_count, bool)
            or not isinstance(exclusions_count, int)
            or exclusions_count < 0
        ):
            raise ValueError("StockBounce v2 coverage exclusions_count is invalid")
        unseeded_count = item.get("unseeded_count")
        if unseeded_count is not None and (
            isinstance(unseeded_count, bool)
            or not isinstance(unseeded_count, int)
            or not 0 <= unseeded_count <= exclusions_count
        ):
            raise ValueError("StockBounce v2 coverage unseeded_count is invalid")


def build_snapshot_v2(
    date_string: str,
    rows: Iterable[dict],
    *,
    coverage: dict,
    max_lookback: int,
) -> dict:
    snapshot = {
        "schema_version": 2,
        "market": "US",
        "date": date_string,
        "max_lookback": max_lookback,
        "rows": sorted((dict(row) for row in rows), key=lambda row: row["ticker"]),
        "coverage": coverage,
    }
    validate_snapshot_v2(snapshot)
    return snapshot


def _coverage(snapshot: dict, universe: str, exclusions: int) -> dict:
    source = snapshot["coverage"][universe]
    return {
        "status": "degraded" if exclusions else source["status"],
        "universe_provenance": source["universe_provenance"],
        "exclusions_count": source["exclusions_count"] + exclusions,
        "unseeded_count": source.get("unseeded_count"),
    }


def evaluate_v2(
    snapshot: dict,
    bars: Iterable[dict],
    *,
    lookback: int,
    start_date=None,
    previous_date=None,
) -> dict:
    """Evaluate both universes from actual T bars and the requested prior window."""
    validate_snapshot_v2(snapshot)
    if (
        isinstance(lookback, bool)
        or not isinstance(lookback, int)
        or not 1 <= lookback <= MAX_LOOKBACK
    ):
        raise ValueError("StockBounce v2 lookback must be between 1 and 1260")
    if lookback > snapshot["max_lookback"]:
        raise UnsupportedLookbackError(lookback, snapshot["max_lookback"])

    target_date = snapshot["date"]
    bars = list(bars)
    previous_dates = set()
    for bar in bars:
        bar_date = _date_value(bar["date"] if "date" in bar else bar["session_date"])
        if bar_date < target_date:
            previous_dates.add(bar_date)
    ordered_dates = sorted(previous_dates)
    if start_date is None or previous_date is None:
        if not ordered_dates and snapshot["rows"]:
            raise ValueError("StockBounce v2 stored session coverage is incomplete")
        start_date = (
            ordered_dates[-min(lookback, len(ordered_dates))] if ordered_dates else None
        )
        previous_date = ordered_dates[-1] if ordered_dates else None
    else:
        start_date = _date_value(start_date)
        previous_date = _date_value(previous_date)
        if not start_date < previous_date < target_date and start_date != previous_date:
            raise ValueError("StockBounce v2 session bounds are invalid")
        if previous_date >= target_date:
            raise ValueError("StockBounce v2 session bounds are invalid")

    indexed = {}
    for bar in bars:
        bar_date = _date_value(bar["date"] if "date" in bar else bar["session_date"])
        if bar_date in (start_date, previous_date):
            indexed[(bar["ticker"], bar_date)] = bar

    selected = {universe: [] for universe in UNIVERSES}
    missing = {universe: 0 for universe in UNIVERSES}
    for row in snapshot["rows"]:
        ticker = row["ticker"]
        start = indexed.get((ticker, start_date))
        previous = indexed.get((ticker, previous_date))
        if start is None or previous is None or float(start["open"]) <= 0:
            for universe in row["universes"]:
                missing[universe] += 1
            continue
        lookback_change = (
            (float(previous["close"]) - float(start["open"]))
            / float(start["open"])
            * 100.0
        )
        open_close_change = (
            (float(row["close"]) - float(row["open"])) / float(row["open"]) * 100.0
        )
        comparison_high = float(row.get("split_adjusted_high", row["high"]))
        if (
            lookback_change >= 0
            or open_close_change <= 0
            or comparison_high <= float(row["previous_all_time_high"])
        ):
            continue
        display = {
            "ticker": ticker,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]),
            "open_close_change_pct": open_close_change,
            "lookback_change_pct": lookback_change,
            "previous_all_time_high": float(row["previous_all_time_high"]),
        }
        for universe in row["universes"]:
            selected[universe].append(display)

    lists = {}
    for universe in UNIVERSES:
        ordered = sorted(
            selected[universe],
            key=lambda row: (-row["open_close_change_pct"], row["ticker"]),
        )[:MAX_ROWS]
        lists[universe] = {
            "rows": [
                {"id": index, **row} for index, row in enumerate(ordered, start=1)
            ],
            "coverage": _coverage(snapshot, universe, missing[universe]),
        }
    return {
        "schema_version": 2,
        "market": "US",
        "date": target_date,
        "lookback": lookback,
        **lists,
    }
