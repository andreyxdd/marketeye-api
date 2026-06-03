"""Seed MongoDB collections from committed JSON fixtures."""

import json
from pathlib import Path

from core.settings import MONGO_DB_NAME
from db.mongodb import AsyncIOMotorClient

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "mongo"


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
