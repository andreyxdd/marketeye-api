"""Partial publish tests when market-wide analytics fails."""

import pytest

import services.publish_service as publish_service


async def _noop_async(*args, **kwargs):
    del args, kwargs
    return None


@pytest.mark.asyncio
async def test_publish_day_skips_market_analytics_but_publishes_lists(monkeypatch):
    upserts = {"artifacts": [], "tickers": []}

    async def market_fail(conn, date):
        del conn, date
        raise RuntimeError("CVI failed")

    async def lists_stub(conn, date, market="US", price_band=None, include_mentions=False):
        del conn, date, market, price_band, include_mentions
        return {
            "by_one_day_avg_mf": [{"ticker": "AAPL"}],
            "by_three_day_avg_mf": [],
            "by_volume": [],
            "by_three_day_avg_volume": [],
            "by_macd": [],
        }

    async def ticker_stub(conn, date, ticker, market="US", include_mentions=False):
        del conn, date, ticker, market, include_mentions
        return {"ticker": "AAPL"}

    async def upsert_artifact_stub(pool, date, artifact_key, payload, market="US"):
        del pool, date, payload, market
        upserts["artifacts"].append(artifact_key)

    async def upsert_ticker_stub(pool, date, ticker_symbol, payload, market="US"):
        del pool, date, payload, market
        upserts["tickers"].append(ticker_symbol)

    monkeypatch.setattr(
        publish_service.analytics_service,
        "get_market_analytics_hot",
        market_fail,
    )
    monkeypatch.setattr(
        publish_service.analytics_service,
        "get_analytics_lists_by_criteria_hot",
        lists_stub,
    )
    monkeypatch.setattr(
        publish_service.analytics_service,
        "get_ticker_analytics_response_hot",
        ticker_stub,
    )
    monkeypatch.setattr(publish_service, "upsert_artifact", upsert_artifact_stub)
    monkeypatch.setattr(publish_service, "upsert_ticker_payload", upsert_ticker_stub)

    result = await publish_service.publish_day(
        conn=object(),
        pool=object(),
        date="2024-06-03",
        market="US",
        include_mentions=False,
    )

    assert publish_service.MARKET_ARTIFACT_KEY not in upserts["artifacts"]
    assert upserts["tickers"] == ["AAPL"]
    assert result["skipped_artifacts"] == [publish_service.MARKET_ARTIFACT_KEY]
    assert result["phase_errors"]


@pytest.mark.asyncio
async def test_publish_day_skips_when_no_tickers(monkeypatch):
    upserts = {"artifacts": [], "tickers": []}

    async def lists_empty(conn, date, market="US", price_band=None, include_mentions=False):
        del conn, date, market, price_band, include_mentions
        return {
            "by_one_day_avg_mf": [],
            "by_three_day_avg_mf": [],
            "by_volume": [],
            "by_three_day_avg_volume": [],
            "by_macd": [],
        }

    async def upsert_artifact_stub(pool, date, artifact_key, payload, market="US"):
        del pool, date, payload, market
        upserts["artifacts"].append(artifact_key)

    monkeypatch.setattr(
        publish_service.analytics_service,
        "get_analytics_lists_by_criteria_hot",
        lists_empty,
    )
    monkeypatch.setattr(publish_service, "upsert_artifact", upsert_artifact_stub)

    result = await publish_service.publish_day(
        conn=object(),
        pool=object(),
        date="2026-06-19",
        market="US",
        include_mentions=False,
    )

    assert result["tickers_written"] == 0
    assert upserts["artifacts"] == []
