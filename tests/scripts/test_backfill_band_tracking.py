"""Unit tests for band-tracking backfill script."""

import pytest

import scripts.backfill_band_tracking as backfill_band_tracking


@pytest.mark.asyncio
async def test_dry_run_calls_neither_put_nor_publish(monkeypatch, capsys):
    calls = []

    async def fake_get_published_dates(pool, market="US"):
        del pool
        return [{"date_string": "2024-06-01"}, {"date_string": "2024-06-03"}]

    async def fake_analytics_exist(conn, date, market):
        del conn
        return True

    async def fake_put(conn, date, market="US"):
        calls.append(("put", date, market))
        return "put"

    async def fake_publish(conn, pool, date, market="US", include_mentions=False):
        calls.append(("publish", date, market, include_mentions))
        return {"artifacts": 1, "tickers": 1}

    monkeypatch.setattr(
        backfill_band_tracking, "get_published_dates", fake_get_published_dates
    )
    monkeypatch.setattr(
        backfill_band_tracking, "analytics_exist", fake_analytics_exist
    )
    monkeypatch.setattr(backfill_band_tracking, "put_top_tickers", fake_put)
    monkeypatch.setattr(backfill_band_tracking, "publish_day", fake_publish)
    monkeypatch.setattr(
        backfill_band_tracking, "connect_mongo", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "close_mongo", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "connect_postgres", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "close_postgres", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "get_mongo_database", lambda: _async_return(object())
    )
    monkeypatch.setattr(
        backfill_band_tracking, "get_postgres_pool", lambda: _async_return(object())
    )

    await backfill_band_tracking.run_backfill(
        markets=["US"], trading_days=15, dry_run=True
    )

    assert calls == []
    out = capsys.readouterr().out
    assert "2024-06-01" in out
    assert "2024-06-03" in out
    assert "dry-run" in out.lower() or "DRY" in out


@pytest.mark.asyncio
async def test_apply_calls_put_then_publish_for_dates_with_analytics(monkeypatch):
    calls = []

    async def fake_get_published_dates(pool, market="US"):
        del pool
        return [
            {"date_string": "2024-05-01"},
            {"date_string": "2024-06-01"},
            {"date_string": "2024-06-03"},
        ]

    async def fake_analytics_exist(conn, date, market):
        del conn, market
        return date in {"2024-06-01", "2024-06-03"}

    async def fake_put(conn, date, market="US"):
        calls.append(("put", date, market))
        return "put"

    async def fake_publish(conn, pool, date, market="US", include_mentions=False):
        calls.append(("publish", date, market))
        return {"artifacts": 1, "tickers": 1}

    monkeypatch.setattr(
        backfill_band_tracking, "get_published_dates", fake_get_published_dates
    )
    monkeypatch.setattr(
        backfill_band_tracking, "analytics_exist", fake_analytics_exist
    )
    monkeypatch.setattr(backfill_band_tracking, "put_top_tickers", fake_put)
    monkeypatch.setattr(backfill_band_tracking, "publish_day", fake_publish)
    monkeypatch.setattr(
        backfill_band_tracking, "connect_mongo", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "close_mongo", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "connect_postgres", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "close_postgres", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "get_mongo_database", lambda: _async_return(object())
    )
    monkeypatch.setattr(
        backfill_band_tracking, "get_postgres_pool", lambda: _async_return(object())
    )

    await backfill_band_tracking.run_backfill(
        markets=["US"], trading_days=2, dry_run=False
    )

    assert calls == [
        ("put", "2024-06-01", "US"),
        ("publish", "2024-06-01", "US"),
        ("put", "2024-06-03", "US"),
        ("publish", "2024-06-03", "US"),
    ]


@pytest.mark.asyncio
async def test_skips_dates_without_analytics(monkeypatch, capsys):
    calls = []

    async def fake_get_published_dates(pool, market="US"):
        del pool
        return [{"date_string": "2024-06-01"}, {"date_string": "2024-06-03"}]

    async def fake_analytics_exist(conn, date, market):
        del conn, market
        return date == "2024-06-03"

    async def fake_put(conn, date, market="US"):
        calls.append(("put", date, market))
        return "put"

    async def fake_publish(conn, pool, date, market="US", include_mentions=False):
        calls.append(("publish", date, market))
        return {"artifacts": 1, "tickers": 1}

    monkeypatch.setattr(
        backfill_band_tracking, "get_published_dates", fake_get_published_dates
    )
    monkeypatch.setattr(
        backfill_band_tracking, "analytics_exist", fake_analytics_exist
    )
    monkeypatch.setattr(backfill_band_tracking, "put_top_tickers", fake_put)
    monkeypatch.setattr(backfill_band_tracking, "publish_day", fake_publish)
    monkeypatch.setattr(
        backfill_band_tracking, "connect_mongo", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "close_mongo", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "connect_postgres", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "close_postgres", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "get_mongo_database", lambda: _async_return(object())
    )
    monkeypatch.setattr(
        backfill_band_tracking, "get_postgres_pool", lambda: _async_return(object())
    )

    await backfill_band_tracking.run_backfill(
        markets=["US"], trading_days=15, dry_run=False
    )

    assert calls == [
        ("put", "2024-06-03", "US"),
        ("publish", "2024-06-03", "US"),
    ]
    out = capsys.readouterr().out
    assert "2024-06-01" in out
    assert "skip" in out.lower()


def test_parse_markets_default_and_normalize():
    assert backfill_band_tracking.parse_markets("US,TO") == ["US", "TO"]
    assert backfill_band_tracking.parse_markets("us, to") == ["US", "TO"]


async def _async_noop():
    return None


async def _async_return(value):
    return value
