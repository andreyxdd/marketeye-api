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

    async def load_bars_after_watermarks(self, tickers, watermarks, before_date):
        del tickers, watermarks, before_date
        return {}

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
    async def fetch_daily_splits(self, date_string):
        del date_string
        return []

    async def fetch_splits(self, ticker, start_date=None, end_date=None):
        del ticker, start_date, end_date
        raise AssertionError("daily publication must not fetch splits per ticker")


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


class _BulkSplitProvider:
    def __init__(self):
        self.calls = []

    async def fetch_daily_splits(self, date_string):
        self.calls.append(date_string)
        return [
            {"code": "AAA", "date": date_string, "split": "2:1"},
            {"code": "OTHER", "date": date_string, "split": "3:1"},
        ]

    async def fetch_splits(self, ticker, start_date=None, end_date=None):
        del ticker, start_date, end_date
        raise AssertionError("daily publication must not fetch splits per ticker")

    async def fetch_range(self, *args):
        raise AssertionError("daily split refresh must not fetch full price history")


@pytest.mark.asyncio
async def test_daily_publication_refreshes_new_splits_without_history_refetch():
    store = _HistoryStore(tickers=("AAA",), macd=())
    provider = _BulkSplitProvider()

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
    assert provider.calls == ["2024-01-19"]
    assert store.splits == {"AAA": [{"date": "2024-01-19", "ratio": 2.0}]}


class _RecoveryStore:
    def __init__(self, bars, watermarks):
        self.bars = list(bars)
        self.watermarks = copy.deepcopy(watermarks)
        self.snapshots = {}
        self.splits = {}
        self.writes = []
        self.range_reads = []

    async def load_snapshot(self, date_string):
        return self.snapshots.get(date_string)

    async def list_macd_tickers(self, before_date):
        del before_date
        return []

    async def load_bars(self, tickers, date_string):
        return {
            ticker: copy.deepcopy(bar)
            for ticker in tickers
            for bar in self.bars
            if bar["ticker"] == ticker and bar["date"] == date_string
        }

    async def load_watermarks(self, tickers):
        return {ticker: self.watermarks.get(ticker) for ticker in tickers}

    async def load_bars_after_watermarks(self, tickers, watermarks, before_date):
        self.range_reads.append(
            (tuple(tickers), copy.deepcopy(watermarks), before_date)
        )
        return {
            ticker: [
                copy.deepcopy(bar)
                for bar in self.bars
                if bar["ticker"] == ticker
                and watermarks.get(ticker) is not None
                and watermarks[ticker]["date"] < bar["date"] < before_date
            ]
            for ticker in tickers
        }

    async def load_splits(self, tickers, watermarks, through_date):
        del watermarks, through_date
        return {ticker: self.splits.get(ticker, []) for ticker in tickers}

    async def persist_splits(self, ticker, splits):
        self.splits[ticker] = copy.deepcopy(splits)

    async def max_lookback(self, date_string):
        del date_string
        return 0

    async def publish(
        self, date_string, snapshot, watermarks, *, current_macd_tickers=()
    ):
        del current_macd_tickers
        self.writes.append((date_string, copy.deepcopy(snapshot)))
        self.snapshots[date_string] = copy.deepcopy(snapshot)
        self.watermarks.update(copy.deepcopy(watermarks))


@pytest.mark.asyncio
async def test_out_of_order_publication_folds_skipped_highs_without_regressing():
    bars = [
        _bar("AAA", "2024-01-22", 125.0),
        _bar("AAA", "2024-01-19", 120.0),
        _bar("AAA", "2024-01-18", 130.0),
    ]
    store = _RecoveryStore(bars, {"AAA": {"date": "2024-01-17", "high": 100.0}})
    provider = _NoSplitProvider()

    for target in ("2024-01-19", "2024-01-22"):
        await publish_us_session_v2(
            _mongo([{"ticker": "AAA"}]),
            object(),
            target,
            history_store=store,
            split_provider=provider,
        )
        if target == "2024-01-19":
            with pytest.raises(RuntimeError, match="verified high history"):
                await publish_us_session_v2(
                    _mongo([{"ticker": "AAA"}]),
                    object(),
                    "2024-01-18",
                    history_store=store,
                    split_provider=provider,
                )
            assert store.watermarks["AAA"] == {
                "date": "2024-01-19",
                "high": 130.0,
            }

    assert store.snapshots["2024-01-19"]["rows"][0]["previous_all_time_high"] == 130.0
    assert store.snapshots["2024-01-22"]["rows"][0]["previous_all_time_high"] == 130.0
    assert store.watermarks["AAA"] == {"date": "2024-01-22", "high": 130.0}
    assert [call[2] for call in store.range_reads] == [
        "2024-01-19",
        "2024-01-18",
        "2024-01-22",
    ]


class _GapSplitProvider:
    def __init__(self, fail_date=None):
        self.calls = []
        self.fail_date = fail_date

    async def fetch_daily_splits(self, date_string):
        self.calls.append(date_string)
        if date_string == self.fail_date:
            raise ValueError("recovered split provider failed")
        if date_string == "2024-01-18":
            return [
                {"code": "AAA", "date": date_string, "split": "2:1"},
                {"code": "OTHER", "date": date_string, "split": "3:1"},
            ]
        return []

    async def fetch_splits(self, ticker, start_date=None, end_date=None):
        del ticker, start_date, end_date
        raise AssertionError("daily publication must not fetch splits per ticker")


@pytest.mark.asyncio
async def test_out_of_order_recovery_applies_skipped_session_split_before_t_and_next():
    store = _RecoveryStore(
        [
            _bar("AAA", "2024-01-22", 125.0),
            _bar("AAA", "2024-01-19", 120.0),
            _bar("AAA", "2024-01-18", 130.0),
        ],
        {"AAA": {"date": "2024-01-17", "high": 200.0}},
    )
    provider = _GapSplitProvider()

    await publish_us_session_v2(
        _mongo([{"ticker": "AAA"}]),
        object(),
        "2024-01-19",
        history_store=store,
        split_provider=provider,
    )
    with pytest.raises(RuntimeError, match="verified high history"):
        await publish_us_session_v2(
            _mongo([{"ticker": "AAA"}]),
            object(),
            "2024-01-18",
            history_store=store,
            split_provider=provider,
        )
    await publish_us_session_v2(
        _mongo([{"ticker": "AAA"}]),
        object(),
        "2024-01-22",
        history_store=store,
        split_provider=provider,
    )

    assert provider.calls == [
        "2024-01-18",
        "2024-01-19",
        "2024-01-18",
        "2024-01-22",
    ]
    assert store.splits == {"AAA": [{"date": "2024-01-18", "ratio": 2.0}]}
    assert store.snapshots["2024-01-19"]["rows"][0]["previous_all_time_high"] == 130.0
    assert store.watermarks["AAA"] == {"date": "2024-01-22", "high": 130.0}
    assert store.snapshots["2024-01-22"]["rows"][0]["previous_all_time_high"] == 130.0


@pytest.mark.asyncio
async def test_gap_split_failure_aborts_before_any_split_or_watermark_write():
    store = _RecoveryStore(
        [
            _bar("AAA", "2024-01-18", 130.0),
            _bar("AAA", "2024-01-19", 120.0),
        ],
        {"AAA": {"date": "2024-01-17", "high": 200.0}},
    )
    provider = _GapSplitProvider(fail_date="2024-01-19")

    with pytest.raises(RuntimeError, match="recovered split provider failed"):
        await publish_us_session_v2(
            _mongo([{"ticker": "AAA"}]),
            object(),
            "2024-01-19",
            history_store=store,
            split_provider=provider,
        )

    assert provider.calls == ["2024-01-18", "2024-01-19"]
    assert store.splits == {}
    assert store.writes == []
    assert store.snapshots == {}
    assert store.watermarks["AAA"] == {"date": "2024-01-17", "high": 200.0}


@pytest.mark.asyncio
async def test_watermark_at_or_after_target_is_excluded_with_degraded_coverage():
    store = _RecoveryStore(
        [
            _bar("AAA", "2024-01-18", 110.0),
            _bar("BBB", "2024-01-18", 105.0),
        ],
        {
            "AAA": {"date": "2024-01-19", "high": 120.0},
            "BBB": {"date": "2024-01-17", "high": 100.0},
        },
    )

    result = await publish_us_session_v2(
        _mongo([{"ticker": "AAA"}, {"ticker": "BBB"}]),
        object(),
        "2024-01-18",
        history_store=store,
        split_provider=_NoSplitProvider(),
    )

    snapshot = store.snapshots["2024-01-18"]
    assert [row["ticker"] for row in snapshot["rows"]] == ["BBB"]
    assert snapshot["rows"][0]["previous_all_time_high"] == 100.0
    assert snapshot["coverage"]["whole_market"] == {
        "status": "degraded",
        "universe_provenance": "mongo_analytics+local_ohlcv",
        "exclusions_count": 1,
        "unseeded_count": 0,
    }
    assert result["coverage"]["whole_market"] == "degraded"
    assert store.watermarks["AAA"] == {"date": "2024-01-19", "high": 120.0}


class _FailOnceBulkProvider:
    def __init__(self):
        self.calls = []

    async def fetch_daily_splits(self, date_string):
        self.calls.append(date_string)
        if len(self.calls) == 1:
            raise ValueError("bulk split provider failed")
        return []

    async def fetch_splits(self, ticker, start_date=None, end_date=None):
        del ticker, start_date, end_date
        raise AssertionError("daily publication must not fetch splits per ticker")


@pytest.mark.asyncio
async def test_bulk_split_failure_leaves_session_unpublished_and_retryable():
    store = _HistoryStore(tickers=("AAA",), macd=())
    provider = _FailOnceBulkProvider()

    with pytest.raises(RuntimeError, match="bulk split provider failed"):
        await publish_us_session_v2(
            _mongo([{"ticker": "AAA"}]),
            object(),
            "2024-01-19",
            history_store=store,
            split_provider=provider,
        )

    assert store.snapshots == {}
    assert store.writes == []
    assert store.watermarks["AAA"] == {"date": "2024-01-18", "high": 110.0}

    await publish_us_session_v2(
        _mongo([{"ticker": "AAA"}]),
        object(),
        "2024-01-19",
        history_store=store,
        split_provider=provider,
    )
    assert provider.calls == ["2024-01-19", "2024-01-19"]
    assert store.snapshots["2024-01-19"]["rows"][0]["previous_all_time_high"] == 110.0


@pytest.mark.asyncio
async def test_eodhd_daily_splits_use_one_validated_bulk_request():
    from services.stock_bounce.adapters import EodhdStockBounceAdapter

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"code": "AAA", "date": "2024-01-19", "split": "2:1"}]

    class _Provider:
        def __init__(self):
            self.urls = []

        def _http_get(self, url):
            self.urls.append(url)
            return _Response()

    provider = _Provider()
    rows = await EodhdStockBounceAdapter(provider).fetch_daily_splits("2024-01-19")

    assert rows == [{"code": "AAA", "date": "2024-01-19", "split": "2:1"}]
    assert len(provider.urls) == 1
    assert (
        "/eod-bulk-last-day/US?type=splits&date=2024-01-19&fmt=json&api_token="
        in provider.urls[0]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"code": "AAA", "date": "2024-01-19", "split": "2:1"},
        [{"code": "AAA", "date": "2024-01-18", "split": "2:1"}],
    ],
)
async def test_eodhd_daily_splits_reject_invalid_shape_or_substituted_date(payload):
    from services.stock_bounce.adapters import EodhdStockBounceAdapter

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class _Provider:
        def _http_get(self, url):
            del url
            return _Response()

    with pytest.raises(ValueError, match="invalid daily splits"):
        await EodhdStockBounceAdapter(_Provider()).fetch_daily_splits("2024-01-19")


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
            row = await conn.fetchrow(
                """
                SELECT as_of_date, high FROM stock_bounce_v2_high_watermarks
                WHERE market = 'US' AND ticker = 'GUARD'
                """
            )
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
