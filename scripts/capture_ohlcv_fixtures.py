#!/usr/bin/env python3
"""
Build OHLCV + golden calc fixtures.

Uses Polygon when POLYGON_API_KEY is set; otherwise generates synthetic bars.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("REDIS_URI", "redis://localhost:6379/1")
os.environ.setdefault("POLYGON_API_KEY", "test-polygon-key")

from tests.helpers.constants import CALC_TICKERS, FIXTURE_DATE  # noqa: E402
from utils.handle_external_apis import get_ticker_analytics  # noqa: E402

MARKET_TICKERS = {
    "US": CALC_TICKERS,
}

OHLCV_DIR = ROOT / "tests" / "fixtures" / "ohlcv"
GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"
GOLDEN_FIELDS = [
    "macd",
    "one_day_avg_mf",
    "three_day_avg_mf",
    "volume",
    "three_day_avg_volume",
    "mfi",
    "ema3",
    "ema9",
    "ema12",
]


def synthetic_polygon_payload(ticker: str, end_date: str, days: int = 100) -> dict:
    tickers = CALC_TICKERS
    end = datetime.strptime(end_date, "%Y-%m-%d")
    results = []
    price = 100.0 + tickers.index(ticker) * 10
    cursor = end
    while len(results) < days:
        if cursor.weekday() < 5:
            price *= 1.001 if len(results) % 2 == 0 else 0.999
            day_utc = datetime(
                cursor.year, cursor.month, cursor.day, 12, 0, 0, tzinfo=timezone.utc
            )
            ts = int(day_utc.timestamp() * 1000)
            results.append(
                {
                    "t": ts,
                    "o": round(price * 0.995, 4),
                    "h": round(price * 1.01, 4),
                    "l": round(price * 0.99, 4),
                    "c": round(price, 4),
                    "v": 1_000_000 + len(results) * 1000,
                }
            )
        cursor -= timedelta(days=1)
    return {"results": results}


def fetch_polygon_payload(ticker: str, end_date: str) -> dict:
    api_key = os.getenv("POLYGON_API_KEY")
    if not api_key or api_key in {"test", "test-polygon-key"}:
        return synthetic_polygon_payload(ticker, end_date)
    end = datetime.strptime(end_date, "%Y-%m-%d")
    start = end - timedelta(days=120)
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker.upper()}/range/1/day/"
        f"{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
        f"?adjusted=true&sort=desc&limit=50000&apiKey={api_key}"
    )
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("results"):
            return synthetic_polygon_payload(ticker, end_date)
        return payload
    except requests.RequestException:
        return synthetic_polygon_payload(ticker, end_date)


def mock_get(url, *args, **kwargs):
    for ticker in CALC_TICKERS:
        if f"/ticker/{ticker.upper()}/" in url:
            payload = json.loads((OHLCV_DIR / f"{ticker}.json").read_text())
            mock_response = requests.Response()
            mock_response.status_code = 200
            mock_response._content = json.dumps(payload).encode("utf-8")
            return mock_response
    raise AssertionError(f"unexpected URL in tests: {url}")


def build_golden(ticker: str) -> dict:
    analytics = get_ticker_analytics(ticker, FIXTURE_DATE)
    return {field: analytics[field] for field in GOLDEN_FIELDS if field in analytics}


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture OHLCV and calc golden fixtures")
    parser.add_argument(
        "--market",
        default="US",
        help="Market code (default: US)",
    )
    args = parser.parse_args()
    market = args.market.upper()
    tickers = MARKET_TICKERS.get(market)
    if not tickers:
        raise SystemExit(f"unsupported market: {market}")

    OHLCV_DIR.mkdir(parents=True, exist_ok=True)
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    for ticker in tickers:
        payload = fetch_polygon_payload(ticker, FIXTURE_DATE)
        (OHLCV_DIR / f"{ticker}.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    with patch("providers.polygon_us.requests.get", side_effect=mock_get):
        for ticker in tickers:
            golden = build_golden(ticker)
            (GOLDEN_DIR / f"{ticker.lower()}_{FIXTURE_DATE}.json").write_text(
                json.dumps(golden, indent=2), encoding="utf-8"
            )

    print(
        f"market={market} wrote OHLCV to {OHLCV_DIR} and golden to {GOLDEN_DIR}"
    )


if __name__ == "__main__":
    main()
