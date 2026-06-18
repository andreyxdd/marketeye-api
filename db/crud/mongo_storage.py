"""Mongo storage ratio and published-gated prune helpers."""

from typing import Optional

import asyncpg
from motor.motor_asyncio import AsyncIOMotorClient

from core.markets import list_markets, normalize_market
from core.settings import MONGO_DB_NAME
from db.crud.analytics import remove_base_analytics
from db.crud.published_archive import is_session_published


async def get_mongo_storage_ratio(
    conn: AsyncIOMotorClient,
    storage_limit_bytes: int,
) -> tuple[int, float]:
    stats = await conn[MONGO_DB_NAME].command("dbStats")
    size_bytes = int(stats.get("dataSize") or stats.get("totalSize") or 0)
    ratio = float(size_bytes) / float(storage_limit_bytes)
    return size_bytes, ratio


async def prune_mongo_session_date(
    conn: AsyncIOMotorClient,
    date: str,
    market: str,
) -> None:
    market = normalize_market(market)
    await remove_base_analytics(conn, date, market=market)
    await remove_base_analytics(conn, date, "tracking", market=market)


async def prune_mongo_if_published(
    pool: asyncpg.Pool,
    conn: AsyncIOMotorClient,
    date: str,
    market: str,
) -> bool:
    if not await is_session_published(pool, date, market):
        return False
    await prune_mongo_session_date(conn, date, market)
    return True


async def prune_oldest_published_mongo_session(
    pool: asyncpg.Pool,
    conn: AsyncIOMotorClient,
) -> Optional[str]:
    async with pool.acquire() as pg_conn:
        row = await pg_conn.fetchrow(
            """
            SELECT session_date
            FROM published_dates
            ORDER BY session_date ASC
            LIMIT 1
            """
        )
        if row is None:
            return None
        session_date = row["session_date"]

    date_string = session_date.isoformat()
    for market in list_markets():
        await prune_mongo_session_date(conn, date_string, market)
    return date_string
