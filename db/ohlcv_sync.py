"""Bounded synchronous PostgreSQL pool for OHLCV provider cache path."""

from __future__ import annotations

import threading
from typing import Optional

from psycopg_pool import ConnectionPool

from core.settings import DATABASE_URL
from db.postgres import normalize_database_url

_pool: Optional[ConnectionPool] = None
_pool_lock = threading.Lock()

OHLCV_SYNC_POOL_MAX_SIZE = 5


def get_ohlcv_sync_pool() -> Optional[ConnectionPool]:
    """Return lazy sync pool; None when DATABASE_URL is unset."""
    global _pool
    if not DATABASE_URL:
        return None

    if _pool is not None:
        return _pool

    with _pool_lock:
        if _pool is not None:
            return _pool
        dsn = normalize_database_url(DATABASE_URL)
        _pool = ConnectionPool(
            conninfo=dsn,
            min_size=1,
            max_size=OHLCV_SYNC_POOL_MAX_SIZE,
            open=True,
        )
        return _pool


def close_ohlcv_sync_pool():
    """Close sync pool (tests / graceful shutdown)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None
