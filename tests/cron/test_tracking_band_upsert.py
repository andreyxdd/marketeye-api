"""Band-scoped tracking upsert: unbanded + each PRICE_BANDS key."""

import pytest

from core.settings import MONGO_DB_NAME
from db.crud import tracking
from utils.price_bands import PRICE_BANDS


@pytest.mark.asyncio
async def test_put_top_tickers_upserts_unbanded_and_all_price_bands(monkeypatch):
    upsert_filters = []

    class CursorStub:
        def sort(self, *args, **kwargs):
            del args, kwargs
            return self

        def limit(self, *args, **kwargs):
            del args, kwargs
            return self

        async def to_list(self, length=None):
            del length
            return [{"ticker": "AAA"}, {"ticker": "BBB"}]

    class AnalyticsCollectionStub:
        def find(self, *args, **kwargs):
            del args, kwargs
            return CursorStub()

    class TrackingCollectionStub:
        async def update_one(self, filt, update, upsert=False):
            del update, upsert
            upsert_filters.append(dict(filt))

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

    await tracking.put_top_tickers(conn, "2024-06-01", market="US")

    # 5 criteria × (1 unbanded + 4 bands)
    assert len(upsert_filters) == len(tracking.CRITERIA) * (1 + len(PRICE_BANDS))

    for criterion in tracking.CRITERIA:
        unbanded = [
            f
            for f in upsert_filters
            if f.get("criterion") == criterion and f.get("price_band") is None
        ]
        assert len(unbanded) == 1
        assert unbanded[0] == {
            "date": 1717200000,
            "criterion": criterion,
            "market": "US",
            "price_band": None,
        }
        for band in PRICE_BANDS:
            banded = [
                f
                for f in upsert_filters
                if f.get("criterion") == criterion and f.get("price_band") == band
            ]
            assert len(banded) == 1
            assert banded[0] == {
                "date": 1717200000,
                "criterion": criterion,
                "market": "US",
                "price_band": band,
            }


@pytest.mark.asyncio
async def test_put_top_tickers_by_criterion_applies_close_filter_for_band(monkeypatch):
    find_queries = []

    class CursorStub:
        def sort(self, *args, **kwargs):
            del args, kwargs
            return self

        def limit(self, *args, **kwargs):
            del args, kwargs
            return self

        async def to_list(self, length=None):
            del length
            return [{"ticker": "CHEAP"}]

    class AnalyticsCollectionStub:
        def find(self, query, *args, **kwargs):
            del args, kwargs
            find_queries.append(query)
            return CursorStub()

    class TrackingCollectionStub:
        async def update_one(self, *args, **kwargs):
            del args, kwargs
            return None

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

    await tracking.put_top_tickers_by_criterion(
        conn, "2024-06-01", "volume", market="US", price_band="lte5"
    )

    assert len(find_queries) == 1
    assert find_queries[0]["close"]["$lte"] == 5.00
    assert "$gte" not in find_queries[0]["close"]
