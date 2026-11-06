"""Canonical StockBounce publication and pure legacy semantics."""

from datetime import date, timedelta

import pandas as pd
import pytest

from db.crud.mongo_storage import prune_mongo_if_published
from db.crud.published_archive import (
    STOCK_BOUNCE_ARTIFACT_KEY,
    get_artifact_payload,
    is_archive_complete,
    upsert_artifact,
    upsert_published_date,
    upsert_ticker_payload,
)
from services.stock_bounce.semantics import (
    build_snapshot,
    build_stock_bounce_analytics,
    evaluate,
)


def _history(changes):
    bars = []
    start = date(2024, 1, 1)
    for index, change in enumerate(changes):
        open_price = 100.0
        bars.append(
            {
                "ticker": "ABC",
                "date": (start + timedelta(days=index)).isoformat(),
                "open": open_price,
                "close": open_price * (1 + change / 100),
                "high": 101.0,
                "low": 99.0,
                "volume": 1000 + index,
            }
        )
    return bars


def _legacy_bounce_oracle(bars):
    df = pd.DataFrame(bars).sort_values(by="date")
    changes = df[["open", "close"]].pct_change(axis=1)["close"]
    return [
        value * 100
        for value in changes.iloc[::-1]
        .cumsum()
        .iloc[::-1]
        .tolist()[-19:-1][::-1]
    ]


def test_legacy_bounce_vector_matches_original_pandas_algorithm():
    bars = _history([1, -2, 3, 4, -5, 2, 1, -1, 6, 2, -3, 1, 4, -2, 2, 3, -1, 2, 5])
    analytics = build_stock_bounce_analytics(bars)
    legacy = _legacy_bounce_oracle(bars)

    assert len(legacy) == 18
    assert analytics["bounce"] == pytest.approx(legacy)
    assert analytics["open_close_change_pct"] == pytest.approx(5.0)
    assert analytics["ticker"] == "ABC"
    assert analytics["volume"] == 1018


def test_snapshot_rejects_incomplete_vectors_and_publishes_full_universe():
    rows = [build_stock_bounce_analytics(_history([1] * 18 + [5]))]
    snapshot = build_snapshot("2024-01-19", rows)

    assert snapshot["coverage"]["status"] == "exact"
    assert snapshot["coverage"]["declared_universe_count"] == 1
    assert len(snapshot["rows"][0]["bounce"]) == 18

    invalid = dict(rows[0])
    invalid["bounce"] = invalid["bounce"][:-1]
    with pytest.raises(ValueError, match="18"):
        build_snapshot("2024-01-19", [invalid])


def test_screening_price_filter_long_period_order_and_frequencies():
    selected = build_stock_bounce_analytics(_history([-2] * 18 + [5]))
    selected["ticker"] = "B"
    other = dict(selected)
    other["ticker"] = "A"
    other["close"] = 100.0
    snapshot = build_snapshot("2024-01-19", [selected, other])

    result = evaluate(snapshot, period=5, price_range="100to299_99")

    assert [row["ticker"] for row in result["rows"]] == ["A", "B"]
    assert result["rows"][0]["open_close_change_pct"] == pytest.approx(5.0)
    assert result["rows"][0]["frequencies"] == ", ".join(
        f"T-{period}" for period in range(3, 18)
    )


@pytest.mark.asyncio
async def test_us_archive_completeness_requires_bounce_but_to_does_not(postgres_pool):
    await upsert_published_date(postgres_pool, "2024-06-03", market="US")
    await upsert_published_date(postgres_pool, "2024-06-03", market="TO")
    for market in ("US", "TO"):
        await upsert_ticker_payload(
            postgres_pool, "2024-06-03", "ABC", {"ticker": "ABC"}, market=market
        )
    await upsert_artifact(
        postgres_pool,
        "2024-06-03",
        "market_analytics",
        {"SP500": 1},
        market="US",
    )

    assert not await is_archive_complete(postgres_pool, "2024-06-03", "US")
    assert await is_archive_complete(postgres_pool, "2024-06-03", "TO")

    await upsert_artifact(
        postgres_pool,
        "2024-06-03",
        STOCK_BOUNCE_ARTIFACT_KEY,
        build_snapshot(
            "2024-06-03",
            [build_stock_bounce_analytics(_history([1] * 18 + [5]))],
        ),
        market="US",
    )
    assert await is_archive_complete(postgres_pool, "2024-06-03", "US")


@pytest.mark.asyncio
async def test_archive_completeness_rejects_malformed_empty_and_invalid_snapshots(
    postgres_pool,
):
    import copy

    valid = build_snapshot(
        "2024-06-03",
        [build_stock_bounce_analytics(_history([1] * 18 + [5]))],
    )
    invalid_snapshots = []
    empty = copy.deepcopy(valid)
    empty["rows"] = []
    empty["coverage"].update(row_count=0, declared_universe_count=0)
    invalid_snapshots.append(empty)
    missing_count = copy.deepcopy(valid)
    del missing_count["coverage"]["declared_universe_count"]
    invalid_snapshots.append(missing_count)
    wrong_count = copy.deepcopy(valid)
    wrong_count["coverage"]["row_count"] = 2
    invalid_snapshots.append(wrong_count)
    invalid_row = copy.deepcopy(valid)
    invalid_row["rows"][0]["bounce"] = invalid_row["rows"][0]["bounce"][:-1]
    invalid_snapshots.append(invalid_row)

    for index, snapshot in enumerate(invalid_snapshots):
        date_string = f"2024-06-{10 + index:02d}"
        await upsert_published_date(postgres_pool, date_string, market="US")
        await upsert_ticker_payload(
            postgres_pool, date_string, "ABC", {"ticker": "ABC"}, market="US"
        )
        await upsert_artifact(
            postgres_pool,
            date_string,
            "market_analytics",
            {"SP500": 1},
            market="US",
        )
        await upsert_artifact(
            postgres_pool,
            date_string,
            STOCK_BOUNCE_ARTIFACT_KEY,
            snapshot,
            market="US",
        )
        assert not await is_archive_complete(postgres_pool, date_string, "US")


@pytest.mark.asyncio
async def test_prune_guard_uses_archive_completeness(monkeypatch):
    calls = []

    async def complete_stub(pool, date_string, market):
        del pool, date_string
        return market == "TO"

    async def prune_stub(conn, date_string, market):
        del conn
        calls.append((date_string, market))

    monkeypatch.setattr("db.crud.mongo_storage.is_archive_complete", complete_stub)
    monkeypatch.setattr("db.crud.mongo_storage.prune_mongo_session_date", prune_stub)

    assert not await prune_mongo_if_published(object(), object(), "2024-06-03", "US")
    assert await prune_mongo_if_published(object(), object(), "2024-06-03", "TO")
    assert calls == [("2024-06-03", "TO")]


@pytest.mark.asyncio
async def test_daily_publisher_is_idempotent_and_publishes_ingested_rows(monkeypatch):
    from core.settings import MONGO_DB_NAME
    from services.stock_bounce import publication

    row = build_stock_bounce_analytics(_history([1] * 18 + [5]))
    row["one_day_open_close_change"] = row.pop("open_close_change_pct") / 100

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def find(self, query):
            del query
            return self

        async def to_list(self, length):
            del length
            return self.rows

    zero_open = {**row, "ticker": "ZRO", "one_day_open_close_change": None}
    conn = {MONGO_DB_NAME: {"analytics": Cursor([row, zero_open])}}
    writes = []

    async def upsert_stub(pool, date_string, key, payload, market):
        del pool
        writes.append((date_string, key, payload, market))

    monkeypatch.setattr(publication, "upsert_artifact", upsert_stub)

    first = await publication.publish_us_session(conn, object(), "2024-01-19")
    second = await publication.publish_us_session(conn, object(), "2024-01-19")

    assert first["rows"] == second["rows"] == 1
    assert len(writes) == 2
    assert writes[0][2] == writes[1][2]
    assert set(writes[0][2]["rows"][0]) == {
        "ticker", "open", "close", "volume", "open_close_change_pct", "bounce"
    }

    empty = {MONGO_DB_NAME: {"analytics": Cursor([])}}
    with pytest.raises(ValueError, match="requires US analytics rows"):
        await publication.publish_us_session(empty, object(), "2024-01-19")
    assert len(writes) == 2
