"""Split-safe high history and idempotent daily StockBounce v2 publication."""

import copy
from datetime import date

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
    def __init__(self, tickers=("AAA", "NEW", "OLD"), macd=("OLD",)):
        self.writes = []
        self.snapshots = {}
        self.splits = {}
        self.watermarks = {
            ticker: {"date": "2024-01-18", "high": high}
            for ticker, high in (("AAA", 110.0), ("NEW", 120.0), ("OLD", 60.0))
            if ticker in tickers
        }
        self.macd = list(macd)

    async def load_snapshot(self, date_string):
        return self.snapshots.get(date_string)

    async def list_macd_tickers(self, before_date):
        assert before_date == "2024-01-19"
        return self.macd

    async def load_bars(self, tickers, date_string):
        return {
            ticker: _bar(ticker, date_string, high)
            for ticker, high in (("AAA", 111.0), ("NEW", 121.0), ("OLD", 61.0))
            if ticker in tickers
        }

    async def load_watermarks(self, tickers):
        return {ticker: self.watermarks.get(ticker) for ticker in tickers}

    async def load_splits(self, tickers, watermarks, through_date):
        del watermarks, through_date
        return {ticker: self.splits.get(ticker, []) for ticker in tickers}

    async def persist_splits(self, ticker, splits):
        by_date = {item["date"]: item for item in self.splits.get(ticker, [])}
        by_date.update({item["date"]: item for item in splits})
        self.splits[ticker] = list(by_date.values())

    async def max_lookback(self, date_string):
        del date_string
        return 17

    async def publish(
        self, date_string, snapshot, watermarks, *, current_macd_tickers=()
    ):
        self.writes.append(
            (date_string, copy.deepcopy(snapshot), copy.deepcopy(watermarks))
        )
        self.snapshots[date_string] = copy.deepcopy(snapshot)
        self.watermarks.update(copy.deepcopy(watermarks))
        self.macd = sorted(set(self.macd) | set(current_macd_tickers))


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query):
        del query
        return self

    async def to_list(self, length):
        del length
        return self.rows


def _mongo(rows):
    from core.settings import MONGO_DB_NAME

    return {MONGO_DB_NAME: {"analytics": _Cursor(rows)}}


class _NoSplitProvider:
    async def fetch_splits(self, ticker, start_date=None, end_date=None):
        del ticker, start_date, end_date
        return []


@pytest.mark.asyncio
async def test_daily_v2_republication_uses_persisted_snapshot_not_advanced_watermark():
    conn = _mongo([{"ticker": "AAA", "macd": 1.0}, {"ticker": "NEW"}])
    store = _HistoryStore()
    provider = _NoSplitProvider()

    first = await publish_us_session_v2(
        conn,
        object(),
        "2024-01-19",
        history_store=store,
        split_provider=provider,
    )
    persisted = copy.deepcopy(store.snapshots["2024-01-19"])
    second = await publish_us_session_v2(
        conn,
        object(),
        "2024-01-19",
        history_store=store,
        split_provider=provider,
    )

    assert first["rows"] == second["rows"] == 3
    assert len(store.writes) == 1
    assert store.snapshots["2024-01-19"] == persisted
    assert store.writes[0][1]["rows"][0]["previous_all_time_high"] == 110.0
    assert store.watermarks["AAA"] == {"date": "2024-01-19", "high": 111.0}


@pytest.mark.asyncio
async def test_macd_symbol_first_seen_on_t_is_not_in_t_minus_one_universe():
    store = _HistoryStore()

    await publish_us_session_v2(
        _mongo([{"ticker": "AAA", "macd": 1.0}, {"ticker": "NEW"}]),
        object(),
        "2024-01-19",
        history_store=store,
        split_provider=_NoSplitProvider(),
    )

    by_ticker = {row["ticker"]: row for row in store.snapshots["2024-01-19"]["rows"]}
    assert by_ticker["AAA"]["universes"] == ["whole_market"]
    assert by_ticker["NEW"]["universes"] == ["whole_market"]
    assert by_ticker["OLD"]["universes"] == ["macd_history"]
    assert "AAA" in store.macd


class _SplitProvider:
    def __init__(self):
        self.calls = []

    async def fetch_splits(self, ticker, start_date=None, end_date=None):
        self.calls.append((ticker, start_date, end_date))
        return [{"date": "2024-01-19", "ratio": 2.0}]

    async def fetch_range(self, *args):
        raise AssertionError("daily split refresh must not fetch full price history")


@pytest.mark.asyncio
async def test_daily_publication_refreshes_new_splits_without_history_refetch():
    store = _HistoryStore(tickers=("AAA",), macd=())
    provider = _SplitProvider()

    await publish_us_session_v2(
        _mongo([{"ticker": "AAA"}]),
        object(),
        "2024-01-19",
        history_store=store,
        split_provider=provider,
    )

    row = store.snapshots["2024-01-19"]["rows"][0]
    assert row["previous_all_time_high"] == 55.0
    assert store.watermarks["AAA"] == {"date": "2024-01-19", "high": 111.0}
    assert provider.calls == [("AAA", "2024-01-18", "2024-01-19")]
    assert store.splits["AAA"] == [{"date": "2024-01-19", "ratio": 2.0}]


@pytest.mark.asyncio
async def test_daily_watermark_upsert_does_not_overwrite_newer_state(postgres_pool):
    from services.stock_bounce.adapters import PostgresStockBounceHistoryStore
    from services.stock_bounce.semantics_v2 import build_snapshot_v2

    store = PostgresStockBounceHistoryStore(postgres_pool)
    coverage = {
        universe: {
            "status": "exact",
            "universe_provenance": "fixture",
            "exclusions_count": 0,
        }
        for universe in ("whole_market", "macd_history")
    }

    async def publish_at(day, high):
        snapshot = build_snapshot_v2(
            day,
            [
                {
                    "ticker": "GUARD",
                    "open": 100.0,
                    "high": high,
                    "close": 101.0,
                    "volume": 1000,
                    "previous_all_time_high": high - 1,
                    "universes": ["whole_market"],
                }
            ],
            coverage=coverage,
            max_lookback=0,
        )
        await store.publish(day, snapshot, {"GUARD": {"date": day, "high": high}})

    await publish_at("2031-01-03", 111.0)
    await publish_at("2031-01-02", 110.0)
    try:
        async with postgres_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT as_of_date, high FROM stock_bounce_v2_high_watermarks
                WHERE market = 'US' AND ticker = 'GUARD'
                """)
        assert row["as_of_date"] == date(2031, 1, 3)
        assert row["high"] == 111.0
    finally:
        async with postgres_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM published_dates WHERE session_date = ANY($1::date[])",
                [date(2031, 1, 2), date(2031, 1, 3)],
            )
            await conn.execute(
                "DELETE FROM stock_bounce_v2_high_watermarks WHERE ticker = 'GUARD'"
            )
            await conn.execute(
                "DELETE FROM stock_bounce_v2_memberships WHERE ticker = 'GUARD'"
            )
