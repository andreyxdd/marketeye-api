#!/usr/bin/env python3
"""Generate committed Mongo and external JSON fixtures for the test suite."""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.helpers.constants import (  # noqa: E402
    BY_CRITERIA_KEYS,
    CRITERIA,
    FIXTURE_DATE,
    FIXTURE_TICKERS,
    HISTORY_WEEKDAYS,
    LIST_LIMIT,
)
from utils.handle_datetimes import get_epoch  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
MONGO_DIR = FIXTURES_DIR / "mongo"
EXTERNAL_DIR = FIXTURES_DIR / "external"


def weekday_dates(anchor: str, count: int) -> list[str]:
    end = pd.Timestamp(anchor)
    dates = pd.bdate_range(end=end, periods=count)
    return [d.strftime("%Y-%m-%d") for d in dates]


def criterion_score(criterion: str, rank: int) -> float:
    base = (CRITERIA.index(criterion) + 1) * 10_000
    return float(base - rank)


def advancing_ticker_count(day_index: int) -> int:
    """Vary advancers per day so CVI slope is non-flat over HISTORY_WEEKDAYS."""
    return 20 + (day_index % 11)


def build_analytics() -> list[dict]:
    docs = []
    dates = weekday_dates(FIXTURE_DATE, HISTORY_WEEKDAYS)
    for day_index, date_str in enumerate(dates):
        epoch = get_epoch(date_str)
        anchor = date_str == FIXTURE_DATE
        adv_count = advancing_ticker_count(day_index)
        for rank, ticker in enumerate(FIXTURE_TICKERS):
            change = 0.015 if rank < adv_count else -0.012
            doc = {
                "ticker": ticker,
                "date": epoch,
                "one_day_open_close_change": change,
            }
            if anchor:
                for criterion in CRITERIA:
                    doc[criterion] = criterion_score(criterion, rank)
            docs.append(doc)
    return docs


def build_scrapes() -> list[dict]:
    epoch = get_epoch(FIXTURE_DATE)
    docs = []
    for index, ticker in enumerate(FIXTURE_TICKERS):
        docs.append(
            {
                "date": epoch,
                "ticker": ticker,
                "mentions": 3 + (index % 5),
            }
        )
    return docs


def build_tracking() -> list[dict]:
    epoch = get_epoch(FIXTURE_DATE)
    docs = []
    for criterion in CRITERIA:
        ordered = sorted(
            FIXTURE_TICKERS,
            key=lambda ticker: criterion_score(
                criterion, FIXTURE_TICKERS.index(ticker)
            ),
            reverse=True,
        )
        docs.append(
            {
                "date": epoch,
                "criterion": criterion,
                "tickers": ordered[:LIST_LIMIT],
            }
        )
    return docs


def stub_extra(ticker: str) -> dict:
    return {
        "macd_2_sessions_ago": 1.1,
        "macd_5_sessions_ago": 1.0,
        "macd_20_sessions_ago": 0.9,
        "one_day_volume_change": 0.01,
        "three_day_avg_volume_change": 0.02,
        "one_day_close_change": 0.005,
        "three_day_avg_close_change": 0.004,
        "ema_3over9": ["up"],
        "ema_12over9": ["up"],
        "ema_12over26": ["up"],
        "ema_50over20": ["up"],
        "closingPriceChangeDay12": 0.01,
        "closingPriceChangeDay23": 0.02,
        "mfi": 55.5,
        "ema3": 100.0,
        "ema9": 99.0,
        "ema12": 98.0,
        "ema20": 97.0,
        "ema26": 96.0,
        "ema50": 95.0,
        "ticker": ticker,
    }


def stub_ticker_analytics(ticker: str) -> dict:
    epoch = get_epoch(FIXTURE_DATE)
    rank = FIXTURE_TICKERS.index(ticker)
    return {
        "ticker": ticker,
        "date": epoch,
        "macd": criterion_score("macd", rank),
        "one_day_avg_mf": criterion_score("one_day_avg_mf", rank),
        "three_day_avg_mf": criterion_score("three_day_avg_mf", rank),
        "volume": criterion_score("volume", rank),
        "three_day_avg_volume": criterion_score("three_day_avg_volume", rank),
        "one_day_open_close_change": 0.01,
        "mentions_over_one_day": 3,
        "mentions_over_two_days": 6,
        "mentions_over_three_days": 9,
        "fcf": "12.3B",
        "frequencies": "T-2, T-4",
        **stub_extra(ticker),
    }


def build_external() -> None:
    ticker_analytics = {
        ticker: stub_ticker_analytics(ticker) for ticker in FIXTURE_TICKERS
    }
    ticker_extra = {ticker: stub_extra(ticker) for ticker in FIXTURE_TICKERS}
    fcf = {ticker: "12.3B" for ticker in FIXTURE_TICKERS}
    sp500 = {"SP500": 5280.5}
    vix = {
        "VIX": 13.2,
        "VIX1": 14.1,
        "VIX2": 15.0,
        "VIX_50days_EMA": 16.5,
    }
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    (EXTERNAL_DIR / "ticker_analytics.json").write_text(
        json.dumps(ticker_analytics, indent=2), encoding="utf-8"
    )
    (EXTERNAL_DIR / "ticker_extra.json").write_text(
        json.dumps(ticker_extra, indent=2), encoding="utf-8"
    )
    (EXTERNAL_DIR / "fcf.json").write_text(json.dumps(fcf, indent=2), encoding="utf-8")
    (EXTERNAL_DIR / "sp500.json").write_text(
        json.dumps(sp500, indent=2), encoding="utf-8"
    )
    (EXTERNAL_DIR / "vix.json").write_text(json.dumps(vix, indent=2), encoding="utf-8")


def write_mongo() -> None:
    MONGO_DIR.mkdir(parents=True, exist_ok=True)
    (MONGO_DIR / "analytics.json").write_text(
        json.dumps(build_analytics(), indent=2), encoding="utf-8"
    )
    (MONGO_DIR / "scrapes.json").write_text(
        json.dumps(build_scrapes(), indent=2), encoding="utf-8"
    )
    (MONGO_DIR / "tracking.json").write_text(
        json.dumps(build_tracking(), indent=2), encoding="utf-8"
    )


def main() -> None:
    write_mongo()
    build_external()
    print(f"Wrote fixtures under {FIXTURES_DIR}")
    print(f"Anchor {FIXTURE_DATE}, tickers={len(FIXTURE_TICKERS)}, criteria={BY_CRITERIA_KEYS}")


if __name__ == "__main__":
    main()
