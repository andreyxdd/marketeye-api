"""Async PostgreSQL pool management."""

from urllib.parse import urlsplit, urlunsplit

import asyncpg

from core.settings import DATABASE_URL


class PostgresDatabase:  # pylint: disable=R0903
    """Holds process-level asyncpg pool."""

    pool: asyncpg.Pool = None


db = PostgresDatabase()


def normalize_database_url(database_url: str) -> str:
    """Normalize Heroku-style postgres:// DSN to asyncpg-compatible scheme."""
    if database_url.startswith("postgres://"):
        parsed = urlsplit(database_url)
        return urlunsplit(
            ("postgresql", parsed.netloc, parsed.path, parsed.query, parsed.fragment)
        )
    return database_url


async def connect():
    """Create global asyncpg pool if not initialized."""
    if db.pool is not None:
        return db.pool

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")

    dsn = normalize_database_url(DATABASE_URL)
    db.pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)
    return db.pool


async def get_pool() -> asyncpg.Pool:
    """Return initialized asyncpg pool."""
    if db.pool is None:
        await connect()
    return db.pool


async def close():
    """Close global asyncpg pool."""
    if db.pool is not None:
        await db.pool.close()
        db.pool = None


async def ping(pool: asyncpg.Pool = None) -> bool:
    """Return True when PostgreSQL responds to `SELECT 1`."""
    active_pool = pool or await get_pool()
    async with active_pool.acquire() as conn:
        value = await conn.fetchval("SELECT 1")
    return value == 1
