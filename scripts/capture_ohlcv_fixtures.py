#!/usr/bin/env python3
"""
Build OHLCV + golden calc fixtures.

Reads POLYGON_API_KEY from repo-root `.env`. Uses Polygon when the key returns
enough bars (>= MIN_BARS); otherwise keeps existing fixture files or synthetic bars.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)
os.environ["REDIS_URI"] = "redis://localhost:6379/1"

from tests.helpers.constants import CALC_TICKERS, FIXTURE_DATE  # noqa: E402
from utils.handle_external_apis import get_ticker_analytics  # noqa: E402

MARKET_TICKERS = {
    "US": CALC_TICKERS,
    "TO": ["SHOP", "RY", "TD"],
}

POLYGON_SYMBOL_ALIASES = {
    "GOOG": "GOOGL",
}

MIN_BARS = 50
MAX_FETCH_ATTEMPTS = 5

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


def _load_existing_payload(ticker: str):
    path = OHLCV_DIR / f"{ticker}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if len(payload.get("results") or []) >= MIN_BARS:
        return payload
    return None


def fetch_polygon_payload(ticker: str, end_date: str) -> dict:
    api_key = os.getenv("POLYGON_API_KEY")
    if not api_key or api_key in {"test", "test-polygon-key"}:
        existing = _load_existing_payload(ticker)
        return existing or synthetic_polygon_payload(ticker, end_date)

    polygon_symbol = POLYGON_SYMBOL_ALIASES.get(ticker.upper(), ticker.upper())
    end = datetime.strptime(end_date, "%Y-%m-%d")
    start = end - timedelta(days=120)
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{polygon_symbol}/range/1/day/"
        f"{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
        f"?adjusted=true&sort=desc&limit=50000&apiKey={api_key}"
    )

    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            response = requests.get(url, timeout=60)
            if response.status_code == 429:
                time.sleep(min(2**attempt, 30))
                continue
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") != "OK":
                raise requests.RequestException(payload.get("error") or payload.get("status"))
            results = payload.get("results") or []
            if len(results) >= MIN_BARS:
                print(f"Polygon: {ticker} ({polygon_symbol}) -> {len(results)} bars")
                return payload
            print(
                f"warning: Polygon returned {len(results)} bars for {ticker} "
                f"(need {MIN_BARS}); keeping existing/synthetic fallback"
            )
            break
        except requests.RequestException as exc:
            message = str(exc).replace(api_key, "***")
            print(
                f"warning: Polygon fetch attempt {attempt}/{MAX_FETCH_ATTEMPTS} "
                f"failed for {ticker}: {message}"
            )
            time.sleep(min(2**attempt, 10))

    existing = _load_existing_payload(ticker)
    if existing:
        print(f"keeping existing fixture for {ticker} ({len(existing['results'])} bars)")
        return existing
    return synthetic_polygon_payload(ticker, end_date)


def mock_get(url, *args, **kwargs):
    for ticker in CALC_TICKERS:
        polygon_symbol = POLYGON_SYMBOL_ALIASES.get(ticker.upper(), ticker.upper())
        if f"/ticker/{polygon_symbol}/" in url or f"/ticker/{ticker.upper()}/" in url:
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
