"""Band-scoped frequency reads for tracking + list enrich."""

import pytest

from core.settings import MONGO_DB_NAME
from db.crud import tracking


@pytest.mark.asyncio
async def test_get_analytics_frequencies_matches_price_band(monkeypatch):
    pipelines = []

    class CursorStub:
        async def to_list(self, length=None):
            del length
            return [{"tickers": ["MSFT"], "date": 1}]

    class TrackingCollectionStub:
        def aggregate(self, pipeline):
            pipelines.append(pipeline)
            return CursorStub()

    class MarketDbStub:
        def __getitem__(self, collection_name):
            if collection_name == tracking.MONGO_TRACKING_COLLECTION:
                return TrackingCollectionStub()
            raise KeyError(collection_name)

    conn = {MONGO_DB_NAME: MarketDbStub()}
    monkeypatch.setattr(tracking, "normalize_market", lambda market: market)
    monkeypatch.setattr(tracking, "market_mongo_filter", lambda market: {"market": market})
    monkeypatch.setattr(tracking, "get_past_date", lambda period, date: "2024-05-01")
    monkeypatch.setattr(tracking, "get_epoch", lambda date: 1000 if date == "2024-05-01" else 2000)

    freqs = await tracking.get_analytics_frequencies(
        conn, "2024-06-01", "macd", "MSFT", market="US", price_band="lte5"
    )
    assert freqs == "T-1"
    match0 = pipelines[0][0]["$match"]
    assert match0["price_band"] == "lte5"


@pytest.mark.asyncio
async def test_get_analytics_frequencies_unbanded_matches_null_or_absent(monkeypatch):
    pipelines = []

    class CursorStub:
        async def to_list(self, length=None):
            del length
            return [{"tickers": ["AAPL"], "date": 1}]

    class TrackingCollectionStub:
        def aggregate(self, pipeline):
            pipelines.append(pipeline)
            return CursorStub()

    class MarketDbStub:
        def __getitem__(self, collection_name):
            if collection_name == tracking.MONGO_TRACKING_COLLECTION:
                return TrackingCollectionStub()
            raise KeyError(collection_name)

    conn = {MONGO_DB_NAME: MarketDbStub()}
    monkeypatch.setattr(tracking, "normalize_market", lambda market: market)
    monkeypatch.setattr(tracking, "market_mongo_filter", lambda market: {"market": market})
    monkeypatch.setattr(tracking, "get_past_date", lambda period, date: "2024-05-01")
    monkeypatch.setattr(tracking, "get_epoch", lambda date: 1000 if date == "2024-05-01" else 2000)

    await tracking.get_analytics_frequencies(
        conn, "2024-06-01", "macd", "AAPL", market="US", price_band=None
    )
    match0 = pipelines[0][0]["$match"]
    assert match0["$or"] == [
        {"price_band": None},
        {"price_band": {"$exists": False}},
    ]
