"""US unbanded frequencies must keep market filter when band also uses $or."""

import pytest

from core.markets import market_mongo_filter
from core.settings import MONGO_DB_NAME
from db.crud import tracking


def _match_retains_us_market(match: dict) -> bool:
    """True when match still constrains to US (incl. legacy missing market)."""
    us_clause = market_mongo_filter("US")
    if match.get("$and"):
        return us_clause in match["$and"]
    # Top-level market key or $or that is the US market filter (not band-only).
    if match.get("market") == "US":
        return True
    return match.get("$or") == us_clause.get("$or")


@pytest.mark.asyncio
async def test_unbanded_us_match_retains_market_under_and(monkeypatch):
    pipelines = []

    class CursorStub:
        async def to_list(self, length=None):
            del length
            return []

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
    monkeypatch.setattr(tracking, "get_past_date", lambda period, date: "2024-05-01")
    monkeypatch.setattr(
        tracking, "get_epoch", lambda date: 1000 if date == "2024-05-01" else 2000
    )

    await tracking.get_analytics_frequencies(
        conn, "2024-06-01", "macd", "AAPL", market="US", price_band=None
    )
    match0 = pipelines[0][0]["$match"]
    assert "$and" in match0
    assert market_mongo_filter("US") in match0["$and"]
    assert {
        "$or": [
            {"price_band": None},
            {"price_band": {"$exists": False}},
        ]
    } in match0["$and"]
    assert _match_retains_us_market(match0)


@pytest.mark.asyncio
async def test_us_to_same_date_docs_do_not_clobber_t1(monkeypatch):
    """TO slot on same calendar day must not steal T-1 when market filter holds."""
    interleaved = [
        {"tickers": ["OTHER"], "date": 1900, "market": "TO", "price_band": None},
        {"tickers": ["MSFT"], "date": 1900, "market": "US", "price_band": None},
        {"tickers": ["OTHER"], "date": 1800, "market": "TO", "price_band": None},
        {"tickers": ["MSFT"], "date": 1800, "market": "US", "price_band": None},
    ]
    pipelines = []

    def _doc_matches_us_unbanded(doc: dict, match: dict) -> bool:
        if not _match_retains_us_market(match):
            return True  # buggy match → both markets leak through
        if doc.get("market") not in ("US", None) and "market" in doc:
            if doc["market"] != "US":
                return False
        band_ok = doc.get("price_band") is None
        return band_ok

    class CursorStub:
        def __init__(self, docs):
            self._docs = docs

        async def to_list(self, length=None):
            del length
            return list(self._docs)

    class TrackingCollectionStub:
        def aggregate(self, pipeline):
            pipelines.append(pipeline)
            match = pipeline[0]["$match"]
            filtered = [d for d in interleaved if _doc_matches_us_unbanded(d, match)]
            return CursorStub(filtered)

    class MarketDbStub:
        def __getitem__(self, collection_name):
            if collection_name == tracking.MONGO_TRACKING_COLLECTION:
                return TrackingCollectionStub()
            raise KeyError(collection_name)

    conn = {MONGO_DB_NAME: MarketDbStub()}
    monkeypatch.setattr(tracking, "get_past_date", lambda period, date: "2024-05-01")
    monkeypatch.setattr(
        tracking, "get_epoch", lambda date: 1000 if date == "2024-05-01" else 2000
    )

    freqs = await tracking.get_analytics_frequencies(
        conn, "2024-06-01", "macd", "MSFT", market="US", price_band=None
    )
    assert "T-1" in freqs
    assert freqs.startswith("T-1")
    # Not even-only from TO-first interleave
    assert freqs != "T-2, T-4"
