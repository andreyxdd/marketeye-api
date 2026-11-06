"""Split-safe high history and idempotent daily StockBounce v2 publication."""

import pytest

from services.stock_bounce.history import (
    advance_high_watermark,
    previous_all_time_high,
)
from services.stock_bounce.publication import publish_us_session_v2


def _bar(ticker, day, high, *, open_price=100.0, close=101.0):
    return {
        "ticker": ticker,
        "date": day,
        "open": open_price,
        "high": high,
        "low": 90.0,
        "close": close,
        "volume": 1000,
    }


def test_split_only_adjustment_rescales_earlier_highs_not_dividends():
    bars = [
        {**_bar("ABC", "2024-01-01", 200.0), "adjusted_close": 1.0},
        {**_bar("ABC", "2024-01-02", 90.0), "adjusted_close": 999.0},
        _bar("ABC", "2024-01-03", 101.0),
    ]
    splits = [{"date": "2024-01-02", "ratio": 2.0}]

    previous = previous_all_time_high(bars, "2024-01-03", splits)

    assert previous == 100.0


def test_incremental_watermark_applies_new_split_before_target_high():
    watermark = {"date": "2024-01-01", "high": 200.0}
    target = _bar("ABC", "2024-01-03", 101.0)
    splits = [{"date": "2024-01-02", "ratio": 2.0}]

    previous, advanced = advance_high_watermark(watermark, target, splits)

    assert previous == 100.0
    assert advanced == {"date": "2024-01-03", "high": 101.0}
    assert watermark == {"date": "2024-01-01", "high": 200.0}


def test_reverse_split_ratio_uses_new_shares_per_old_share():
    bars = [_bar("ABC", "2024-01-01", 10.0)]
    splits = [{"date": "2024-01-02", "numerator": 1, "denominator": 2}]

    assert previous_all_time_high(bars, "2024-01-03", splits) == 20.0


class _HistoryStore:
    def __init__(self):
        self.writes = []

    async def list_macd_tickers(self, before_date):
        assert before_date == "2024-01-19"
        return ["OLD"]

    async def load_bars(self, tickers, date_string):
        del tickers
        return {
            ticker: _bar(ticker, date_string, high)
            for ticker, high in (("AAA", 111.0), ("NEW", 121.0), ("OLD", 61.0))
        }

    async def load_watermarks(self, tickers):
        del tickers
        return {
            "AAA": {"date": "2024-01-18", "high": 110.0},
            "NEW": {"date": "2024-01-18", "high": 120.0},
            "OLD": {"date": "2024-01-18", "high": 60.0},
        }

    async def load_splits(self, tickers, watermarks, through_date):
        del tickers, watermarks, through_date
        return {}

    async def max_lookback(self, date_string):
        del date_string
        return 17

    async def publish(self, date_string, snapshot, watermarks):
        self.writes.append((date_string, snapshot, watermarks))


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query):
        del query
        return self

    async def to_list(self, length):
        del length
        return self.rows


@pytest.mark.asyncio
async def test_daily_v2_publication_carries_macd_history_and_is_idempotent():
    from core.settings import MONGO_DB_NAME

    rows = [
        {"ticker": "AAA", "macd": 1.0},
        {"ticker": "NEW"},
    ]
    conn = {MONGO_DB_NAME: {"analytics": _Cursor(rows)}}
    store = _HistoryStore()

    first = await publish_us_session_v2(
        conn, object(), "2024-01-19", history_store=store
    )
    second = await publish_us_session_v2(
        conn, object(), "2024-01-19", history_store=store
    )

    assert first["artifact_key"] == "stock_bounce:v2"
    assert first["rows"] == 3
    assert len(store.writes) == 2
    assert store.writes[0][1] == store.writes[1][1]
    snapshot = store.writes[0][1]
    by_ticker = {row["ticker"]: row for row in snapshot["rows"]}
    assert by_ticker["AAA"]["universes"] == ["whole_market", "macd_history"]
    assert by_ticker["NEW"]["universes"] == ["whole_market"]
    assert by_ticker["OLD"]["universes"] == ["macd_history"]
    assert by_ticker["OLD"]["high"] == 61.0
    assert snapshot["max_lookback"] == 17
    assert store.writes[0][2]["AAA"]["high"] == 111.0
