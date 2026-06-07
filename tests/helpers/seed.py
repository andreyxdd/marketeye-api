"""Seed MongoDB collections from committed JSON fixtures."""

import json
from pathlib import Path

from core.settings import MONGO_DB_NAME
from db.mongodb import AsyncIOMotorClient
from tests.helpers.constants import FIXTURE_DATE, FIXTURE_TICKERS
from utils.handle_datetimes import get_epoch

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "mongo"
FIXTURE_EPOCH = get_epoch(FIXTURE_DATE)

FIXTURE_CLOSE_OVERRIDES = {
    "AAPL": 4.99,
    "MSFT": 5.00,
    "GOOG": 5.01,
}


def _derive_close(doc: dict) -> dict:
    if doc.get("close") is not None:
        return doc
    ticker = doc.get("ticker")
    if ticker not in FIXTURE_TICKERS:
        return doc
    if doc.get("date") != FIXTURE_EPOCH:
        return doc
    if ticker in FIXTURE_CLOSE_OVERRIDES:
        doc["close"] = FIXTURE_CLOSE_OVERRIDES[ticker]
        return doc
    idx = FIXTURE_TICKERS.index(ticker)
    doc["close"] = round(2.0 + idx * 0.95, 2)
    return doc


async def clear_collections(conn: AsyncIOMotorClient) -> None:
    for name in ("analytics", "scrapes", "tracking"):
        await conn[MONGO_DB_NAME][name].delete_many({})


async def seed_collections(conn: AsyncIOMotorClient) -> None:
    await clear_collections(conn)
    for filename, collection in (
        ("analytics.json", "analytics"),
        ("scrapes.json", "scrapes"),
        ("tracking.json", "tracking"),
    ):
        path = FIXTURES_DIR / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            docs = json.load(handle)
        if collection == "analytics":
            docs = [_derive_close(dict(doc)) for doc in docs]
        if docs:
            await conn[MONGO_DB_NAME][collection].insert_many(docs)


async def seed_support_collections(conn: AsyncIOMotorClient) -> None:
    """Seed scrapes + tracking without analytics (pipeline tests)."""
    for filename, collection in (
        ("scrapes.json", "scrapes"),
        ("tracking.json", "tracking"),
    ):
        path = FIXTURES_DIR / filename
        with path.open(encoding="utf-8") as handle:
            docs = json.load(handle)
        if docs:
            await conn[MONGO_DB_NAME][collection].insert_many(docs)
