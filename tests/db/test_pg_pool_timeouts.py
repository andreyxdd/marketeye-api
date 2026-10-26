"""Postgres pools must fail fast on dead TCP connections."""

import pytest
from psycopg_pool import ConnectionPool

import db.postgres as postgres
from db.ohlcv_sync import close_ohlcv_sync_pool, get_ohlcv_sync_pool


@pytest.fixture(autouse=True)
def _reset_ohlcv_sync_pool():
    close_ohlcv_sync_pool()
    yield
    close_ohlcv_sync_pool()


def test_sync_pool_has_tcp_timeouts_and_checks_connections():
    pool = get_ohlcv_sync_pool()

    assert pool.kwargs == {
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
        "tcp_user_timeout": 30000,
        "connect_timeout": 10,
    }
    # psycopg_pool exposes no public accessor for the check callback.
    assert pool._check is ConnectionPool.check_connection  # pylint: disable=protected-access


@pytest.mark.asyncio
async def test_asyncpg_pool_uses_command_timeout(monkeypatch):
    captured = {}

    async def create_pool_spy(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(postgres.db, "pool", None)
    monkeypatch.setattr(postgres.asyncpg, "create_pool", create_pool_spy)

    await postgres.connect()

    assert captured["command_timeout"] == 60
