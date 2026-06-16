"""Route analytics reads between Mongo hot window and PostgreSQL archive."""

from datetime import datetime, timedelta
from typing import Optional

import asyncpg
from fastapi import HTTPException

from core.markets import DEFAULT_MARKET, market_mongo_filter, normalize_market
from core.settings import MONGO_DB_NAME, MONGO_HOT_WINDOW_DAYS
from db.crud.analytics import MONGO_COLLECTION_NAME
from db.crud.published_archive import (
    MARKET_ARTIFACT_KEY,
    build_criterion_artifact_key,
    build_lists_artifact_key,
    get_artifact_payload,
    get_latest_published_date,
    get_published_dates,
    get_ticker_payload,
)
from utils.handle_datetimes import get_date_string, get_epoch


async def _latest_mongo_date(conn, market: str) -> Optional[str]:
    market = normalize_market(market)
    cursor = (
        conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME]
        .find(
            market_mongo_filter(market),
            {"_id": False, "date": True},
        )
        .sort("date", -1)
        .limit(1)
    )
    rows = await cursor.to_list(length=1)
    if not rows:
        return None
    return get_date_string(rows[0]["date"])


def _max_date(left: Optional[str], right: Optional[str]) -> Optional[str]:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


async def is_hot_date(
    conn,
    pool: asyncpg.Pool,
    date: str,
    market: str = DEFAULT_MARKET,
) -> bool:
    """Return True if date is in Mongo hot window near latest available date."""
    market = normalize_market(market)
    latest_mongo = await _latest_mongo_date(conn, market=market)
    latest_pg = await get_latest_published_date(pool, market=market) if pool else None
    latest_date = _max_date(latest_mongo, latest_pg)
    if latest_date is None:
        return True

    latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")
    target_dt = datetime.strptime(date, "%Y-%m-%d")
    hot_floor = latest_dt - timedelta(days=MONGO_HOT_WINDOW_DAYS)
    return target_dt >= hot_floor


def _missing_cold_payload(endpoint_name: str, date: str, market: str):
    raise HTTPException(
        status_code=404,
        detail=(
            f"{endpoint_name}: archive payload missing for market={market}, date={date}"
        ),
    )


async def get_dates_union(conn, pool: asyncpg.Pool, market: str = DEFAULT_MARKET) -> list:
    market = normalize_market(market)
    pipeline = [
        {"$match": market_mongo_filter(market)},
        {"$group": {"_id": "$date"}},
        {"$sort": {"_id": 1}},
    ]
    cursor = conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].aggregate(pipeline)
    mongo_epochs = [doc["_id"] for doc in await cursor.to_list(length=10000)]

    pg_dates = await get_published_dates(pool, market=market) if pool else []
    epochs = set(mongo_epochs)
    for item in pg_dates:
        epochs.add(get_epoch(item["date_string"]))

    sorted_epochs = sorted(epochs)
    return [{"epoch": epoch, "date_string": get_date_string(epoch)} for epoch in sorted_epochs]


async def get_analytics_lists_by_criteria_cold(
    pool: asyncpg.Pool,
    date: str,
    market: str = DEFAULT_MARKET,
    price_band: Optional[str] = None,
) -> dict:
    market = normalize_market(market)
    payload = await get_artifact_payload(
        pool,
        date,
        build_lists_artifact_key(price_band),
        market=market,
    )
    if payload is None:
        _missing_cold_payload("get_analytics_lists_by_criteria", date, market)
    return payload


async def get_analytics_sorted_by_cold(
    pool: asyncpg.Pool,
    date: str,
    criterion: str,
    market: str = DEFAULT_MARKET,
    price_band: Optional[str] = None,
) -> list:
    market = normalize_market(market)
    payload = await get_artifact_payload(
        pool,
        date,
        build_criterion_artifact_key(criterion, price_band),
        market=market,
    )
    if payload is None or criterion not in payload:
        _missing_cold_payload("get_analytics_lists_by_criterion", date, market)
    return payload[criterion]


async def get_ticker_analytics_cold(
    pool: asyncpg.Pool,
    date: str,
    ticker: str,
    market: str = DEFAULT_MARKET,
) -> dict:
    market = normalize_market(market)
    payload = await get_ticker_payload(pool, date, ticker, market=market)
    if payload is None:
        _missing_cold_payload("get_ticker_analytics", date, market)
    return payload


async def get_market_analytics_cold(
    pool: asyncpg.Pool,
    date: str,
    market: str = DEFAULT_MARKET,
) -> dict:
    market = normalize_market(market)
    payload = await get_artifact_payload(
        pool,
        date,
        MARKET_ARTIFACT_KEY,
        market=market,
    )
    if payload is None:
        _missing_cold_payload("get_market_analytics", date, market)
    return payload
