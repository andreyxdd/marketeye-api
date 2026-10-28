"""Pure StockBounce vector construction, evaluation, and snapshot validation."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Iterable, Optional


PRICE_RANGES = {
    "all": (None, None),
    "48to99_99": (48.0, 99.99),
    "100to299_99": (100.0, 299.99),
    "300to499_99": (300.0, 499.99),
    "500to1000": (500.0, 1000.0),
}


def _date_value(value) -> str:
    if isinstance(value, str):
        return value[:10]
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return datetime.utcfromtimestamp(float(value) / 1000).strftime("%Y-%m-%d")


def _change(bar: dict) -> float:
    open_price = float(bar["open"])
    return (float(bar["close"]) - open_price) / open_price * 100


def build_stock_bounce_analytics(bars: Iterable[dict]) -> dict:
    ordered = sorted(bars, key=lambda bar: _date_value(bar["date"]))
    if len(ordered) < 19:
        raise ValueError("StockBounce requires a target bar and 18 preceding trading bars")
    target = ordered[-1]
    previous = ordered[-19:-1]
    changes = [_change(bar) for bar in previous]
    bounce = [sum(changes[index:]) for index in range(18)]
    return {
        "ticker": str(target["ticker"]).upper(),
        "open": float(target["open"]),
        "close": float(target["close"]),
        "volume": int(target["volume"]),
        "open_close_change_pct": _change(target),
        "bounce": bounce,
    }


def _validate_row(row: dict) -> None:
    required = ("ticker", "open", "close", "volume", "open_close_change_pct", "bounce")
    missing = [field for field in required if field not in row]
    if missing:
        raise ValueError(f"StockBounce row is missing fields: {', '.join(missing)}")
    if len(row["bounce"]) != 18 or not all(
        isinstance(value, (int, float)) and math.isfinite(value)
        for value in row["bounce"]
    ):
        raise ValueError(f"StockBounce row {row['ticker']} must have 18 finite bounce values")
    if not all(
        isinstance(row[field], (int, float)) and math.isfinite(row[field])
        for field in ("open", "close", "open_close_change_pct")
    ):
        raise ValueError(f"StockBounce row {row['ticker']} has invalid prices")


def build_snapshot(
    date_string: str,
    rows: Iterable[dict],
    *,
    coverage: str = "exact",
    universe_provenance: str = "mongo_analytics",
    declared_universe_count: Optional[int] = None,
    exclusions: Optional[list[dict]] = None,
) -> dict:
    materialized = sorted((dict(row) for row in rows), key=lambda row: row["ticker"])
    if not materialized:
        raise ValueError("StockBounce snapshot requires a non-empty declared universe")
    tickers = [row["ticker"] for row in materialized]
    if len(set(tickers)) != len(tickers):
        raise ValueError("StockBounce snapshot contains duplicate tickers")
    for row in materialized:
        _validate_row(row)
    excluded = list(exclusions or [])
    declared = (
        len(materialized) + len(excluded)
        if declared_universe_count is None
        else declared_universe_count
    )
    if declared != len(materialized) + len(excluded):
        raise ValueError("StockBounce coverage counts do not match snapshot rows")
    if coverage not in ("exact", "degraded"):
        raise ValueError("StockBounce coverage must be exact or degraded")
    if coverage == "exact" and excluded:
        raise ValueError("Exact StockBounce snapshots cannot contain coverage exclusions")
    return {
        "schema_version": 1,
        "market": "US",
        "date": date_string,
        "rows": materialized,
        "coverage": {
            "status": coverage,
            "universe_provenance": universe_provenance,
            "declared_universe_count": declared,
            "row_count": len(materialized),
            "exclusions": excluded,
        },
    }


def validate_snapshot(snapshot: dict) -> None:
    if snapshot.get("schema_version") != 1 or snapshot.get("market") != "US":
        raise ValueError("Unsupported StockBounce snapshot")
    datetime.strptime(snapshot["date"], "%Y-%m-%d")
    coverage = snapshot.get("coverage") or {}
    if coverage.get("status") not in ("exact", "degraded"):
        raise ValueError("StockBounce snapshot has incomplete coverage metadata")
    if coverage.get("row_count") != len(snapshot.get("rows") or []):
        raise ValueError("StockBounce snapshot coverage row count is invalid")
    for row in snapshot["rows"]:
        _validate_row(row)


def _in_price_range(row: dict, price_range: str) -> bool:
    minimum, maximum = PRICE_RANGES[price_range]
    close = float(row["close"])
    return (minimum is None or close >= minimum) and (
        maximum is None or close <= maximum
    )


def _eligible(row: dict, period: int) -> bool:
    change = float(row["open_close_change_pct"])
    if row["bounce"][period - 1] >= 0 or change <= 0:
        return False
    return period <= 4 or all(change > value for value in row["bounce"])


def _screen(rows: list[dict], period: int, price_range: str) -> list[dict]:
    matches = [
        row
        for row in rows
        if _in_price_range(row, price_range) and _eligible(row, period)
    ]
    return sorted(
        matches,
        key=lambda row: (-float(row["open_close_change_pct"]), row["ticker"]),
    )[:20]


def _display_row(row: dict, display_id: int, frequencies: str) -> dict:
    return {
        "id": display_id,
        "ticker": row["ticker"],
        "open": row["open"],
        "close": row["close"],
        "volume": row["volume"],
        "open_close_change_pct": row["open_close_change_pct"],
        "frequencies": frequencies,
    }


def evaluate(
    snapshot: dict,
    *,
    period: int,
    price_range: str = "all",
    tickers: Optional[list[str]] = None,
) -> dict:
    validate_snapshot(snapshot)
    if not 1 <= period <= 18:
        raise ValueError("StockBounce period must be between 1 and 18")
    if price_range not in PRICE_RANGES:
        raise ValueError("Unsupported StockBounce price range")
    rows = snapshot["rows"]
    membership = {
        current_period: {
            row["ticker"] for row in _screen(rows, current_period, price_range)
        }
        for current_period in range(1, 18)
    }

    def frequencies(ticker: str) -> str:
        return ", ".join(
            f"T-{current_period}"
            for current_period in range(1, 18)
            if ticker in membership[current_period]
        )

    if tickers is None:
        selected = _screen(rows, period, price_range)
        missing = []
    else:
        by_ticker = {row["ticker"]: row for row in rows}
        selected = [by_ticker[ticker] for ticker in tickers if ticker in by_ticker]
        missing = [ticker for ticker in tickers if ticker not in by_ticker]
    return {
        "schema_version": 1,
        "market": "US",
        "date": snapshot["date"],
        "period": period,
        "price_range": price_range,
        "rows": [
            _display_row(row, index, frequencies(row["ticker"]))
            for index, row in enumerate(selected, start=1)
        ],
        "missing_tickers": missing,
        "coverage": snapshot["coverage"]["status"],
    }
