"""Partial publish tests when market-wide analytics fails."""

from unittest.mock import MagicMock

import pytest

import services.analytics_service as analytics_service
import services.publish_service as publish_service
from utils import handle_external_apis as external


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
async def test_publish_day_writes_market_analytics_when_mi_fails_eodhd_ok(
    monkeypatch,
):
    """MI 500 for SP500/VIX + EODHD OK → market_analytics still published."""
    upserts = {"artifacts": [], "tickers": []}
    client = MagicMock()
    client.get.return_value = None
    monkeypatch.setattr(external.cache, "client", client)

    def mi_fail(url, label):
        raise Exception(f"MI 500 ({label})")

    def eodhd_closes(symbol, from_date, to_date):
        del from_date, to_date
        if symbol == external.EODHD_SP500_INDEX:
            return [4000.0, 4100.0, 4200.5]
        if symbol == external.EODHD_VIX_INDEX:
            return [float(i) for i in range(1, 56)]
        raise AssertionError(f"unexpected symbol {symbol}")

    async def cvi_stub(db, date):
        del db, date
        return 0.12

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
        del pool, date, market
        upserts["artifacts"].append(artifact_key)
        if artifact_key == publish_service.MARKET_ARTIFACT_KEY:
            upserts["market_payload"] = payload

    async def upsert_ticker_stub(pool, date, ticker_symbol, payload, market="US"):
        del pool, date, payload, market
        upserts["tickers"].append(ticker_symbol)

    monkeypatch.setattr(external, "_market_insider_request", mi_fail)
    monkeypatch.setattr(external, "_fetch_eodhd_index_closes", eodhd_closes)
    monkeypatch.setattr(analytics_service, "get_normalazied_cvi_slope", cvi_stub)
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

    assert publish_service.MARKET_ARTIFACT_KEY in upserts["artifacts"]
    assert publish_service.MARKET_ARTIFACT_KEY not in result["skipped_artifacts"]
    assert not any(err.startswith("market_analytics:") for err in result["phase_errors"])
    assert upserts["market_payload"]["SP500"] == 4200.5
    assert upserts["market_payload"]["VIX"] == 55.0
    assert upserts["market_payload"]["normalazied_CVI_slope"] == 0.12


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
