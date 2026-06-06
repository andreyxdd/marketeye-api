"""Tests for analytics batch insert behavior."""

import pytest

from core.settings import MONGO_DB_NAME
from db.crud.analytics import MONGO_COLLECTION_NAME, insert_analytics_batch
from utils.handle_datetimes import get_epoch


@pytest.mark.asyncio
async def test_insert_analytics_batch_counts_partial_inserts_on_duplicate(mongo_client):
    collection = mongo_client[MONGO_DB_NAME][MONGO_COLLECTION_NAME]
    await collection.delete_many({"ticker": {"$in": ["DUPTEST", "DUPTEST2"]}})
    await collection.create_index(
        [("ticker", 1), ("date", 1), ("market", 1)],
        unique=True,
        name="test_ticker_date_market_unique",
    )

    epoch = get_epoch("2024-06-03")
    existing = {
        "ticker": "DUPTEST",
        "date": epoch,
        "market": "US",
        "macd": 1.0,
        "volume": 100,
    }
    await collection.insert_one(existing)

    batch = [
        existing,
        {
            "ticker": "DUPTEST",
            "date": epoch,
            "market": "US",
            "macd": 2.0,
            "volume": 200,
        },
        {
            "ticker": "DUPTEST2",
            "date": epoch,
            "market": "US",
            "macd": 3.0,
            "volume": 300,
        },
    ]

    inserted = await insert_analytics_batch(mongo_client, batch, batch_size=10)
    assert inserted == 1
    assert await collection.count_documents({"ticker": "DUPTEST2"}) == 1

    await collection.delete_many({"ticker": {"$in": ["DUPTEST", "DUPTEST2"]}})
