"""Tests for Mongo error propagation in tracking CRUD helpers."""

import pytest

from core.settings import MONGO_DB_NAME
from db.crud import tracking


@pytest.mark.asyncio
async def test_put_top_tickers_by_criterion_propagates_atlas_error(monkeypatch):
    class CursorStub:
        def sort(self, *args, **kwargs):
            del args, kwargs
            return self

        def limit(self, *args, **kwargs):
            del args, kwargs
            return self

        async def to_list(self, length=None):
            del length
            return [{"ticker": "AAPL"}]

    class AnalyticsCollectionStub:
        def find(self, *args, **kwargs):
            del args, kwargs
            return CursorStub()

    class TrackingCollectionStub:
        async def update_one(self, *args, **kwargs):
            del args, kwargs
            raise Exception("AtlasError quota exceeded")

    class MarketDbStub:
        def __getitem__(self, collection_name):
            if collection_name == tracking.MONGO_ANALYTICS_COLLECTION:
                return AnalyticsCollectionStub()
            if collection_name == tracking.MONGO_TRACKING_COLLECTION:
                return TrackingCollectionStub()
            raise KeyError(collection_name)

    conn = {MONGO_DB_NAME: MarketDbStub()}

    monkeypatch.setattr(tracking, "get_epoch", lambda date: 1717200000)
    monkeypatch.setattr(tracking, "normalize_market", lambda market: market)
    monkeypatch.setattr(tracking, "market_mongo_filter", lambda market: {"market": market})

    with pytest.raises(Exception) as exc_info:
        await tracking.put_top_tickers_by_criterion(
            conn,
            "2024-06-01",
            "volume",
            market="US",
        )

    message = str(exc_info.value)
    assert "reported an error" not in message
    assert "AtlasError" in message or "quota" in message


@pytest.mark.asyncio
async def test_put_top_tickers_propagates_atlas_error(monkeypatch):
    async def failing_criterion(conn, date, criterion, lim=None, market="US"):
        del conn, date, lim, market
        if criterion == "volume":
            raise Exception("AtlasError quota exceeded")
        return ["AAPL"]

    monkeypatch.setattr(tracking, "put_top_tickers_by_criterion", failing_criterion)

    with pytest.raises(Exception) as exc_info:
        await tracking.put_top_tickers(object(), "2024-06-01", market="US")

    message = str(exc_info.value)
    assert "AtlasError" in message or "quota" in message
    assert "reported an error" not in message
