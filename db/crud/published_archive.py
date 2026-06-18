"""CRUD helpers for PostgreSQL published read-model archive."""

import json
from datetime import date as date_type
from typing import Optional

import asyncpg

from core.markets import DEFAULT_MARKET, normalize_market
from core.settings import PG_STORAGE_LIMIT_BYTES


def _decode_payload(payload):
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


def _to_date(date_value):
    if isinstance(date_value, date_type):
        return date_value
    return date_type.fromisoformat(date_value)


def build_lists_artifact_key(price_band: Optional[str]) -> str:
    return f"lists_by_criteria:{price_band or 'all'}"


def build_criterion_artifact_key(criterion: str, price_band: Optional[str]) -> str:
    return f"lists_by_criterion:{criterion}:{price_band or 'all'}"


MARKET_ARTIFACT_KEY = "market_analytics"


async def upsert_published_date(
    pool: asyncpg.Pool, date_string: str, market: str = DEFAULT_MARKET
):
    market = normalize_market(market)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO published_dates(session_date, market)
            VALUES($1, $2)
            ON CONFLICT (session_date, market)
            DO UPDATE SET published_at = NOW()
            """,
            _to_date(date_string),
            market,
        )


async def upsert_artifact(
    pool: asyncpg.Pool,
    date_string: str,
    artifact_key: str,
    payload: dict,
    market: str = DEFAULT_MARKET,
):
    market = normalize_market(market)
    await upsert_published_date(pool, date_string, market=market)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO published_artifacts(session_date, market, artifact_key, payload)
            VALUES($1, $2, $3, $4::jsonb)
            ON CONFLICT (session_date, market, artifact_key)
            DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()
            """,
            _to_date(date_string),
            market,
            artifact_key,
            json.dumps(payload),
        )


async def upsert_ticker_payload(
    pool: asyncpg.Pool,
    date_string: str,
    ticker: str,
    payload: dict,
    market: str = DEFAULT_MARKET,
):
    market = normalize_market(market)
    await upsert_published_date(pool, date_string, market=market)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO published_tickers(session_date, market, ticker, payload)
            VALUES($1, $2, $3, $4::jsonb)
            ON CONFLICT (session_date, market, ticker)
            DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()
            """,
            _to_date(date_string),
            market,
            ticker,
            json.dumps(payload),
        )


async def get_artifact_payload(
    pool: asyncpg.Pool,
    date_string: str,
    artifact_key: str,
    market: str = DEFAULT_MARKET,
) -> Optional[dict]:
    market = normalize_market(market)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT payload
            FROM published_artifacts
            WHERE session_date = $1
              AND market = $2
              AND artifact_key = $3
            """,
            _to_date(date_string),
            market,
            artifact_key,
        )
    if row is None:
        return None
    return _decode_payload(row["payload"])


async def get_ticker_payload(
    pool: asyncpg.Pool,
    date_string: str,
    ticker: str,
    market: str = DEFAULT_MARKET,
) -> Optional[dict]:
    market = normalize_market(market)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT payload
            FROM published_tickers
            WHERE session_date = $1
              AND market = $2
              AND ticker = $3
            """,
            _to_date(date_string),
            market,
            ticker,
        )
    if row is None:
        return None
    return _decode_payload(row["payload"])


async def get_published_dates(
    pool: asyncpg.Pool, market: str = DEFAULT_MARKET
) -> list[dict]:
    market = normalize_market(market)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT session_date
            FROM published_dates
            WHERE market = $1
            ORDER BY session_date ASC
            """,
            market,
        )
    return [
        {
            "date_string": row["session_date"].isoformat(),
        }
        for row in rows
    ]


async def is_session_published(
    pool: asyncpg.Pool, date: str, market: str = DEFAULT_MARKET
) -> bool:
    market = normalize_market(market)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 1
            FROM published_dates
            WHERE session_date = $1
              AND market = $2
            """,
            _to_date(date),
            market,
        )
    return row is not None


async def get_latest_published_date(
    pool: asyncpg.Pool, market: str = DEFAULT_MARKET
) -> Optional[str]:
    market = normalize_market(market)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT session_date
            FROM published_dates
            WHERE market = $1
            ORDER BY session_date DESC
            LIMIT 1
            """,
            market,
        )
    if row is None:
        return None
    return row["session_date"].isoformat()


async def get_storage_ratio(
    pool: asyncpg.Pool,
    storage_limit_bytes: int = PG_STORAGE_LIMIT_BYTES,
) -> tuple[int, float]:
    async with pool.acquire() as conn:
        size_bytes = await conn.fetchval("SELECT pg_database_size(current_database())")
    ratio = float(size_bytes) / float(storage_limit_bytes)
    return int(size_bytes), ratio


async def prune_oldest_session_date(pool: asyncpg.Pool) -> Optional[str]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
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
        await conn.execute(
            "DELETE FROM published_dates WHERE session_date = $1", session_date
        )
    return session_date.isoformat()


async def truncate_published_tables(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            TRUNCATE TABLE
                published_tickers,
                published_artifacts,
                published_dates
            RESTART IDENTITY CASCADE
            """
        )
