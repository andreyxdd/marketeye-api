"""Regression: embedded mongo storage monitor must not close cron Postgres pool."""

import pytest

import scripts.mongo_storage_monitor as mongo_storage_monitor
from db.postgres import get_pool as get_postgres_pool


@pytest.mark.asyncio
async def test_embedded_run_monitor_leaves_postgres_pool_open(
    postgres_pool, mongo_client, monkeypatch
):
    del postgres_pool, mongo_client

    async def ratio_stub(conn, limit):
        del conn, limit
        return 100, 0.1

    monkeypatch.setattr(
        mongo_storage_monitor, "get_mongo_storage_ratio", ratio_stub
    )

    pool_before = await get_postgres_pool()
    await mongo_storage_monitor.run_monitor(manage_connections=False)
    pool_after = await get_postgres_pool()

    assert pool_before is pool_after
    async with pool_after.acquire() as conn:
        assert await conn.fetchval("SELECT 1") == 1


@pytest.mark.asyncio
async def test_standalone_run_monitor_closes_connections(monkeypatch):
    calls = {"close_postgres": 0, "close_mongo": 0}

    async def ratio_stub(conn, limit):
        del conn, limit
        return 100, 0.1

    async def connect_postgres_stub():
        return None

    async def connect_mongo_stub():
        return None

    async def close_postgres_stub():
        calls["close_postgres"] += 1

    async def close_mongo_stub():
        calls["close_mongo"] += 1

    async def pool_stub():
        return object()

    async def mongo_stub():
        return object()

    monkeypatch.setattr(
        mongo_storage_monitor, "get_mongo_storage_ratio", ratio_stub
    )
    monkeypatch.setattr(
        mongo_storage_monitor, "connect_postgres", connect_postgres_stub
    )
    monkeypatch.setattr(mongo_storage_monitor, "connect_mongo", connect_mongo_stub)
    monkeypatch.setattr(mongo_storage_monitor, "close_postgres", close_postgres_stub)
    monkeypatch.setattr(mongo_storage_monitor, "close_mongo", close_mongo_stub)
    monkeypatch.setattr(mongo_storage_monitor, "get_postgres_pool", pool_stub)
    monkeypatch.setattr(mongo_storage_monitor, "get_mongo_database", mongo_stub)

    await mongo_storage_monitor.run_monitor(manage_connections=True)

    assert calls["close_postgres"] == 1
    assert calls["close_mongo"] == 1
