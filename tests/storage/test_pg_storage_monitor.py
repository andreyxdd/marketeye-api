"""Unit tests for PostgreSQL storage monitor script."""

import pytest

import scripts.pg_storage_monitor as pg_storage_monitor


async def _noop_async(*args, **kwargs):
    del args, kwargs
    return None


@pytest.mark.asyncio
async def test_pg_storage_monitor_below_threshold(monkeypatch):
    calls = {"notify": 0, "prune": 0}

    async def ratio_stub(pool, limit):
        del pool, limit
        return 100, 0.42

    async def prune_stub(pool):
        del pool
        calls["prune"] += 1
        return "2024-01-01"

    async def pool_stub():
        return object()

    monkeypatch.setattr(pg_storage_monitor, "connect_postgres", _noop_async)
    monkeypatch.setattr(pg_storage_monitor, "close_postgres", _noop_async)
    monkeypatch.setattr(pg_storage_monitor, "get_postgres_pool", pool_stub)
    monkeypatch.setattr(pg_storage_monitor, "get_storage_ratio", ratio_stub)
    monkeypatch.setattr(pg_storage_monitor, "prune_oldest_session_date", prune_stub)
    monkeypatch.setattr(
        pg_storage_monitor,
        "notify_developer",
        lambda **kwargs: calls.__setitem__("notify", calls["notify"] + 1),
    )

    result = await pg_storage_monitor.run_monitor(check_only=False)
    assert result["ratio"] == 0.42
    assert calls["notify"] == 0
    assert calls["prune"] == 0


@pytest.mark.asyncio
async def test_pg_storage_monitor_check_only_alerts_without_prune(monkeypatch):
    calls = {"notify": 0, "prune": 0}

    async def ratio_stub(pool, limit):
        del pool, limit
        return 100, 0.90

    async def prune_stub(pool):
        del pool
        calls["prune"] += 1
        return "2024-01-01"

    async def pool_stub():
        return object()

    monkeypatch.setattr(pg_storage_monitor, "connect_postgres", _noop_async)
    monkeypatch.setattr(pg_storage_monitor, "close_postgres", _noop_async)
    monkeypatch.setattr(pg_storage_monitor, "get_postgres_pool", pool_stub)
    monkeypatch.setattr(pg_storage_monitor, "get_storage_ratio", ratio_stub)
    monkeypatch.setattr(pg_storage_monitor, "prune_oldest_session_date", prune_stub)
    monkeypatch.setattr(
        pg_storage_monitor,
        "notify_developer",
        lambda **kwargs: calls.__setitem__("notify", calls["notify"] + 1),
    )

    result = await pg_storage_monitor.run_monitor(check_only=True)
    assert result["ratio"] == 0.90
    assert calls["notify"] == 1
    assert calls["prune"] == 0


@pytest.mark.asyncio
async def test_pg_storage_monitor_prunes_until_target(monkeypatch):
    calls = {"notify": 0}
    ratios = iter([(1000, 0.90), (900, 0.80), (700, 0.69)])
    pruned = iter(["2024-01-01", "2024-01-02"])

    async def ratio_stub(pool, limit):
        del pool, limit
        return next(ratios)

    async def prune_stub(pool):
        del pool
        return next(pruned)

    async def pool_stub():
        return object()

    monkeypatch.setattr(pg_storage_monitor, "connect_postgres", _noop_async)
    monkeypatch.setattr(pg_storage_monitor, "close_postgres", _noop_async)
    monkeypatch.setattr(pg_storage_monitor, "get_postgres_pool", pool_stub)
    monkeypatch.setattr(pg_storage_monitor, "get_storage_ratio", ratio_stub)
    monkeypatch.setattr(pg_storage_monitor, "prune_oldest_session_date", prune_stub)
    monkeypatch.setattr(
        pg_storage_monitor,
        "notify_developer",
        lambda **kwargs: calls.__setitem__("notify", calls["notify"] + 1),
    )

    result = await pg_storage_monitor.run_monitor(check_only=False)
    assert calls["notify"] == 1
    assert result["pruned_dates"] == ["2024-01-01", "2024-01-02"]
    assert result["ratio"] == 0.69
