"""Scheduled full-history seeding for tickers new to StockBounce v2."""

import asyncio
import copy

import pytest

from services.stock_bounce.publication import publish_us_session_v2
from services.stock_bounce.seeding import seed_us_session_v2
from services.stock_bounce.semantics_v2 import evaluate_v2


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


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query):
        del query
        return self

    async def to_list(self, length):
        del length
        return self.rows


def _mongo(tickers):
    from core.settings import MONGO_DB_NAME

    return {
        MONGO_DB_NAME: {
            "analytics": _Cursor([{"ticker": ticker} for ticker in tickers])
        }
    }


class _SeedStore:
    def __init__(self, bars, watermarks=None, macd=()):
        self.bars = list(bars)
        self.watermarks = copy.deepcopy(watermarks or {})
        self.macd = list(macd)
        self.splits = {}
        self.snapshots = {}
        self.seed_calls = []

    async def load_snapshot(self, date_string):
        return self.snapshots.get(date_string)

    async def list_macd_tickers(self, before_date):
        del before_date
        return list(self.macd)

    async def load_bars(self, tickers, date_string):
        return {
            ticker: copy.deepcopy(bar)
            for ticker in tickers
            for bar in self.bars
            if bar["ticker"] == ticker and bar["date"] == date_string
        }

    async def load_watermarks(self, tickers):
        return {
            ticker: copy.deepcopy(self.watermarks[ticker])
            for ticker in tickers
            if ticker in self.watermarks
        }

    async def load_bars_after_watermarks(self, tickers, watermarks, before_date):
        return {
            ticker: [
                copy.deepcopy(bar)
                for bar in self.bars
                if bar["ticker"] == ticker
                and ticker in watermarks
                and watermarks[ticker]["date"] < bar["date"] < before_date
            ]
            for ticker in tickers
        }

    async def load_splits(self, tickers, watermarks, through_date):
        del watermarks
        return {
            ticker: [
                copy.deepcopy(split)
                for split in self.splits.get(ticker, [])
                if split["date"] <= through_date
            ]
            for ticker in tickers
        }

    async def persist_splits(self, ticker, splits):
        by_date = {item["date"]: item for item in self.splits.get(ticker, [])}
        by_date.update({item["date"]: copy.deepcopy(item) for item in splits})
        self.splits[ticker] = list(by_date.values())

    async def seed(self, ticker, watermark, splits):
        self.seed_calls.append((ticker, copy.deepcopy(watermark)))
        self.watermarks.setdefault(ticker, copy.deepcopy(watermark))
        await self.persist_splits(ticker, splits)

    async def max_lookback(self, date_string):
        del date_string
        return 20

    async def publish(
        self, date_string, snapshot, watermarks, *, current_macd_tickers=()
    ):
        del current_macd_tickers
        self.snapshots[date_string] = copy.deepcopy(snapshot)
        self.watermarks.update(copy.deepcopy(watermarks))


class _HistoryProvider:
    def __init__(self, bars, splits=None, failures=()):
        self.bars = bars
        self.splits = splits or {}
        self.failures = set(failures)
        self.range_calls = []
        self.active = 0
        self.max_active = 0

    async def fetch_range(self, ticker, start_date, end_date):
        self.range_calls.append((ticker, start_date, end_date))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.001)
            if ticker in self.failures:
                raise ValueError(f"mock history failure for {ticker}")
            return [
                copy.deepcopy(bar)
                for bar in self.bars.get(ticker, [])
                if bar["ticker"] == ticker and bar["date"] <= end_date
            ]
        finally:
            self.active -= 1

    async def fetch_splits(self, ticker):
        return copy.deepcopy(self.splits.get(ticker, []))

    async def fetch_daily_splits(self, date_string):
        del date_string
        return []


async def _seed_and_publish(store, provider, day, tickers):
    seed_report = await seed_us_session_v2(
        _mongo(tickers),
        object(),
        day,
        history_store=store,
        remote_bars=provider,
        retry_attempts=1,
    )
    publish_report = await publish_us_session_v2(
        _mongo(tickers),
        object(),
        day,
        history_store=store,
        split_provider=provider,
    )
    return seed_report, publish_report


@pytest.mark.asyncio
async def test_newcomer_full_history_seeds_ath_and_can_qualify_on_target_session():
    days = ("2021-01-04", "2022-01-03", "2023-01-03", "2024-01-18")
    bars = [
        _bar("NEW", days[0], 80.0),
        _bar("NEW", days[1], 200.0),
        _bar("NEW", days[2], 120.0),
        _bar("NEW", days[3], 110.0, close=99.0),
        _bar("NEW", "2024-01-19", 121.0, close=102.0),
    ]
    store = _SeedStore(bars)
    provider = _HistoryProvider(
        {"NEW": bars},
        {"NEW": [{"date": "2023-01-02", "ratio": 2.0}]},
    )

    seed_report, _ = await _seed_and_publish(store, provider, "2024-01-19", ["NEW"])

    assert seed_report["seeded_count"] == 1
    assert seed_report["failed_count"] == 0
    assert provider.range_calls == [("NEW", None, "2024-01-19")]
    assert store.seed_calls[0][1] == {"date": "2024-01-18", "high": 120.0}
    assert store.splits["NEW"] == [{"date": "2023-01-02", "ratio": 2.0}]
    snapshot = store.snapshots["2024-01-19"]
    assert snapshot["rows"][0]["previous_all_time_high"] == 120.0
    result = evaluate_v2(snapshot, bars, lookback=1)
    assert [row["ticker"] for row in result["whole_market"]["rows"]] == ["NEW"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "highs",
    [
        {
            "AAA": [99.0, 100.0, 110.0, 105.0],
            "BBB": [91.0, 90.0, 89.0, 95.0],
        },
        {
            "AAA": [101.0, 100.0, 99.0, 101.0],
            "BBB": [89.0, 90.0, 100.0, 99.0],
        },
    ],
)
async def test_every_usable_ticker_is_seeded_and_later_sessions_advance(highs):
    days = ("2024-01-16", "2024-01-17", "2024-01-18", "2024-01-19")
    bars = [
        _bar(ticker, day, high)
        for ticker, values in highs.items()
        for day, high in zip(days, values)
    ]
    store = _SeedStore(bars)
    provider = _HistoryProvider({ticker: bars for ticker in highs})

    initial = await seed_us_session_v2(
        _mongo(sorted(highs)),
        object(),
        days[0],
        history_store=store,
        remote_bars=provider,
        retry_attempts=1,
    )
    assert initial["no_prior_history_count"] == len(highs)

    for index, day in enumerate(days[1:], start=1):
        seed_report, publish_report = await _seed_and_publish(
            store, provider, day, sorted(highs)
        )
        assert seed_report["failed_count"] == 0
        assert publish_report["rows"] == len(highs)
        for ticker, values in highs.items():
            assert store.watermarks[ticker] == {
                "date": day,
                "high": max(values[: index + 1]),
            }
            row = next(
                row for row in store.snapshots[day]["rows"] if row["ticker"] == ticker
            )
            assert row["previous_all_time_high"] == max(values[:index])

    assert len(provider.range_calls) == 2 * len(highs)
    assert not any(call[2] > days[1] for call in provider.range_calls)


@pytest.mark.asyncio
async def test_failed_seed_is_counted_without_blocking_existing_or_new_tickers():
    bars = [
        _bar("OLD", "2024-01-17", 100.0),
        _bar("OLD", "2024-01-18", 110.0),
        _bar("BAD", "2024-01-17", 90.0),
        _bar("BAD", "2024-01-18", 120.0),
        _bar("NEW", "2024-01-17", 80.0),
        _bar("NEW", "2024-01-18", 81.0),
    ]
    store = _SeedStore(bars, {"OLD": {"date": "2024-01-17", "high": 100.0}})
    provider = _HistoryProvider(
        {ticker: bars for ticker in ("OLD", "BAD", "NEW")}, failures=("BAD",)
    )

    seed_report, _ = await _seed_and_publish(
        store, provider, "2024-01-18", ["OLD", "BAD", "NEW"]
    )

    assert seed_report["candidates_count"] == 2
    assert seed_report["seeded_count"] == 1
    assert seed_report["failed_count"] == 1
    assert set(seed_report["errors"]) == {"BAD"}
    assert {call[0] for call in provider.range_calls} == {"BAD", "NEW"}
    assert store.watermarks["OLD"] == {"date": "2024-01-18", "high": 110.0}
    snapshot = store.snapshots["2024-01-18"]
    assert [row["ticker"] for row in snapshot["rows"]] == ["NEW", "OLD"]
    assert snapshot["coverage"]["whole_market"]["exclusions_count"] == 1
    assert snapshot["coverage"]["whole_market"]["unseeded_count"] == 1
    assert snapshot["coverage"]["macd_history"]["unseeded_count"] == 0


@pytest.mark.asyncio
async def test_listing_without_prior_bars_stays_excluded_then_seeds_next_session():
    bars = [
        _bar("OLD", "2024-01-17", 100.0),
        _bar("OLD", "2024-01-18", 101.0),
        _bar("OLD", "2024-01-19", 102.0),
        _bar("IPO", "2024-01-18", 50.0),
        _bar("IPO", "2024-01-19", 51.0),
    ]
    store = _SeedStore(bars, {"OLD": {"date": "2024-01-17", "high": 100.0}})
    provider = _HistoryProvider({ticker: bars for ticker in ("OLD", "IPO")})

    first_seed, _ = await _seed_and_publish(
        store, provider, "2024-01-18", ["OLD", "IPO"]
    )

    assert first_seed["no_prior_history_count"] == 1
    assert "IPO" not in store.watermarks
    first = store.snapshots["2024-01-18"]
    assert [row["ticker"] for row in first["rows"]] == ["OLD"]
    assert first["coverage"]["whole_market"]["unseeded_count"] == 1

    second_seed, _ = await _seed_and_publish(
        store, provider, "2024-01-19", ["OLD", "IPO"]
    )

    assert second_seed["seeded_count"] == 1
    assert store.watermarks["IPO"] == {"date": "2024-01-19", "high": 51.0}
    second = store.snapshots["2024-01-19"]
    assert {row["ticker"] for row in second["rows"]} == {"OLD", "IPO"}
    assert second["coverage"]["whole_market"]["unseeded_count"] == 0


@pytest.mark.asyncio
async def test_seeding_worker_pool_is_bounded():
    tickers = [f"T{index}" for index in range(6)]
    bars = [
        _bar(ticker, day, high)
        for ticker in tickers
        for day, high in (("2024-01-17", 100.0), ("2024-01-18", 101.0))
    ]
    store = _SeedStore(bars)
    provider = _HistoryProvider({ticker: bars for ticker in tickers})

    report = await seed_us_session_v2(
        _mongo(tickers),
        object(),
        "2024-01-18",
        history_store=store,
        remote_bars=provider,
        retry_attempts=1,
        max_concurrency=2,
    )

    assert report["seeded_count"] == len(tickers)
    assert provider.max_active == 2


@pytest.mark.asyncio
async def test_postgres_seed_is_atomic_and_never_replaces_existing_watermark(
    postgres_pool,
):
    from services.stock_bounce.adapters import PostgresStockBounceHistoryStore

    store = PostgresStockBounceHistoryStore(postgres_pool)
    ticker = "SEEDGUARD"
    try:
        await store.seed(
            ticker,
            {"date": "2031-02-01", "high": 100.0},
            [{"date": "2031-02-01", "ratio": 2.0}],
        )
        await store.seed(
            ticker,
            {"date": "2031-02-02", "high": 999.0},
            [{"date": "2031-02-01", "ratio": 3.0}],
        )
        loaded = await store.load_watermarks([ticker])
        splits = await store.load_splits([ticker], loaded, "2031-02-02")

        assert loaded[ticker] == {"date": "2031-02-01", "high": 100.0}
        assert splits[ticker] == [{"date": "2031-02-01", "ratio": 3.0}]
    finally:
        async with postgres_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM stock_bounce_v2_high_watermarks WHERE ticker = $1",
                ticker,
            )
            await conn.execute(
                "DELETE FROM stock_bounce_v2_splits WHERE ticker = $1",
                ticker,
            )


@pytest.mark.asyncio
async def test_unseeded_macd_member_retries_after_leaving_current_analytics():
    bars = [
        _bar("NEW", "2024-01-17", 100.0),
        _bar("NEW", "2024-01-18", 110.0),
        _bar("NEW", "2024-01-19", 120.0),
    ]
    store = _SeedStore(bars, macd=("NEW",))
    provider = _HistoryProvider({"NEW": bars}, failures=("NEW",))

    first = await seed_us_session_v2(
        _mongo(["NEW"]),
        object(),
        "2024-01-18",
        history_store=store,
        remote_bars=provider,
        retry_attempts=1,
    )
    provider.failures.remove("NEW")
    second = await seed_us_session_v2(
        _mongo([]),
        object(),
        "2024-01-19",
        history_store=store,
        remote_bars=provider,
        retry_attempts=1,
    )

    assert first["failed_count"] == 1
    assert second["candidates_count"] == 1
    assert second["seeded_count"] == 1
    assert second["failed_count"] == 0
    assert store.watermarks["NEW"] == {"date": "2024-01-18", "high": 110.0}
    assert [call[0] for call in provider.range_calls] == ["NEW", "NEW"]


@pytest.mark.asyncio
async def test_full_history_and_split_requests_set_connect_and_read_timeouts():
    from services.stock_bounce.adapters import EodhdStockBounceAdapter

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return []

    class _Provider:
        def __init__(self):
            self.calls = []

        def _http_get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return _Response()

    provider = _Provider()
    adapter = EodhdStockBounceAdapter(provider)
    await adapter.fetch_range("NEW", None, "2024-01-19")
    await adapter.fetch_splits("NEW")

    assert len(provider.calls) == 2
    assert "/eod/NEW.US" in provider.calls[0][0]
    assert "/splits/NEW.US" in provider.calls[1][0]
    for _, kwargs in provider.calls:
        assert kwargs["timeout"] == (10, 60)
        assert all(0 < value < float("inf") for value in kwargs["timeout"])
