"""Canonical StockBounce publication and pure legacy semantics."""

from datetime import date, timedelta

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
from services.stock_bounce import build_snapshot, build_stock_bounce_analytics, evaluate


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


def test_legacy_bounce_vector_and_current_fields_are_literal_parity():
    analytics = build_stock_bounce_analytics(_history([1] * 18 + [5]))

    assert analytics["open_close_change_pct"] == pytest.approx(5.0)
    assert analytics["bounce"] == pytest.approx(list(range(18, 0, -1)))
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
    selected = build_stock_bounce_analytics(_history([-1] * 18 + [5]))
    selected["ticker"] = "B"
    other = dict(selected)
    other["ticker"] = "A"
    other["close"] = 100.0
    snapshot = build_snapshot("2024-01-19", [selected, other])

    result = evaluate(snapshot, period=5, price_range="100to299_99")

    assert [row["ticker"] for row in result["rows"]] == ["A", "B"]
    assert result["rows"][0]["open_close_change_pct"] == pytest.approx(5.0)
    assert result["rows"][0]["frequencies"] == "T-1, T-2, T-3, T-4, T-5, T-6, T-7, T-8, T-9, T-10, T-11, T-12, T-13, T-14, T-15, T-16, T-17"


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
        {"schema_version": 1, "rows": [], "coverage": {"status": "exact"}},
        market="US",
    )
    assert await is_archive_complete(postgres_pool, "2024-06-03", "US")


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
async def test_daily_publisher_is_idempotent_and_refuses_partial_universe(monkeypatch):
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

    conn = {MONGO_DB_NAME: {"analytics": Cursor([row])}}
    writes = []

    async def upsert_stub(pool, date_string, key, payload, market):
        del pool
        writes.append((date_string, key, payload, market))

    monkeypatch.setattr(publication, "get_tickers", lambda date, market: ["ABC"])
    monkeypatch.setattr(publication, "upsert_artifact", upsert_stub)

    first = await publication.publish_us_session(conn, object(), "2024-01-19")
    second = await publication.publish_us_session(conn, object(), "2024-01-19")

    assert first["rows"] == second["rows"] == 1
    assert len(writes) == 2
    assert writes[0][2] == writes[1][2]

    monkeypatch.setattr(publication, "get_tickers", lambda date, market: ["ABC", "XYZ"])
    with pytest.raises(ValueError, match="incomplete provider coverage"):
        await publication.publish_us_session(conn, object(), "2024-01-19")
    assert len(writes) == 2
