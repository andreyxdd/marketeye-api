"""Unit tests for Mongo storage monitor script."""

import pytest

import scripts.mongo_storage_monitor as mongo_storage_monitor


async def _noop_async(*args, **kwargs):
    del args, kwargs
    return None


@pytest.mark.asyncio
async def test_mongo_storage_monitor_below_threshold(monkeypatch):
    calls = {"notify": 0, "prune": 0}

    async def ratio_stub(conn, limit):
        del conn, limit
        return 100, 0.42

    async def prune_stub(pool, conn):
        del pool, conn
        calls["prune"] += 1
        return "2024-01-01"

    async def pool_stub():
        return object()

    async def mongo_stub():
        return object()

    monkeypatch.setattr(mongo_storage_monitor, "connect_postgres", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "close_postgres", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "connect_mongo", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "close_mongo", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "get_postgres_pool", pool_stub)
    monkeypatch.setattr(mongo_storage_monitor, "get_mongo_database", mongo_stub)
    monkeypatch.setattr(mongo_storage_monitor, "get_mongo_storage_ratio", ratio_stub)
    monkeypatch.setattr(
        mongo_storage_monitor,
        "prune_oldest_published_mongo_session",
        prune_stub,
    )
    monkeypatch.setattr(
        mongo_storage_monitor,
        "notify_developer",
        lambda **kwargs: calls.__setitem__("notify", calls["notify"] + 1),
    )

    result = await mongo_storage_monitor.run_monitor(check_only=False)
    assert result["ratio"] == 0.42
    assert calls["notify"] == 0
    assert calls["prune"] == 0


@pytest.mark.asyncio
async def test_mongo_storage_monitor_check_only_alerts_without_prune(monkeypatch):
    calls = {"notify": 0, "prune": 0}

    async def ratio_stub(conn, limit):
        del conn, limit
        return 100, 0.90

    async def prune_stub(pool, conn):
        del pool, conn
        calls["prune"] += 1
        return "2024-01-01"

    async def pool_stub():
        return object()

    async def mongo_stub():
        return object()

    monkeypatch.setattr(mongo_storage_monitor, "connect_postgres", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "close_postgres", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "connect_mongo", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "close_mongo", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "get_postgres_pool", pool_stub)
    monkeypatch.setattr(mongo_storage_monitor, "get_mongo_database", mongo_stub)
    monkeypatch.setattr(mongo_storage_monitor, "get_mongo_storage_ratio", ratio_stub)
    monkeypatch.setattr(
        mongo_storage_monitor,
        "prune_oldest_published_mongo_session",
        prune_stub,
    )
    monkeypatch.setattr(
        mongo_storage_monitor,
        "notify_developer",
        lambda **kwargs: calls.__setitem__("notify", calls["notify"] + 1),
    )

    result = await mongo_storage_monitor.run_monitor(check_only=True)
    assert result["ratio"] == 0.90
    assert calls["notify"] == 1
    assert calls["prune"] == 0


@pytest.mark.asyncio
async def test_mongo_storage_monitor_prunes_until_target(monkeypatch):
    calls = {"notify": 0}
    ratios = iter([(1000, 0.90), (900, 0.80), (700, 0.69)])
    prune_calls = []
    pruned = iter(["2024-01-01", "2024-01-02"])

    async def ratio_stub(conn, limit):
        del conn, limit
        return next(ratios)

    async def prune_stub(pool, conn, exclude_dates=None):
        del pool, conn
        prune_calls.append(list(exclude_dates or []))
        return next(pruned)

    async def pool_stub():
        return object()

    async def mongo_stub():
        return object()

    monkeypatch.setattr(mongo_storage_monitor, "connect_postgres", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "close_postgres", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "connect_mongo", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "close_mongo", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "get_postgres_pool", pool_stub)
    monkeypatch.setattr(mongo_storage_monitor, "get_mongo_database", mongo_stub)
    monkeypatch.setattr(mongo_storage_monitor, "get_mongo_storage_ratio", ratio_stub)
    monkeypatch.setattr(
        mongo_storage_monitor,
        "prune_oldest_published_mongo_session",
        prune_stub,
    )
    monkeypatch.setattr(
        mongo_storage_monitor,
        "notify_developer",
        lambda **kwargs: calls.__setitem__("notify", calls["notify"] + 1),
    )

    result = await mongo_storage_monitor.run_monitor(check_only=False)
    assert calls["notify"] == 1
    assert result["pruned_dates"] == ["2024-01-01", "2024-01-02"]
    assert result["ratio"] == 0.69
    assert prune_calls == [[], ["2024-01-01"]]


@pytest.mark.asyncio
async def test_mongo_storage_monitor_passes_exclude_and_stops_on_none(monkeypatch):
    """After prune, next call excludes pruned dates; None → stop (no duplicate hang)."""
    calls = {"notify": 0, "prune": 0}
    # Stay above target after first prune so loop asks for next date.
    ratios = iter([(1000, 0.90), (900, 0.85)])
    prune_calls = []

    async def ratio_stub(conn, limit):
        del conn, limit
        return next(ratios)

    async def prune_stub(pool, conn, exclude_dates=None):
        del pool, conn
        calls["prune"] += 1
        exclude = list(exclude_dates or [])
        prune_calls.append(exclude)
        if not exclude:
            return "2024-01-01"
        return None

    async def pool_stub():
        return object()

    async def mongo_stub():
        return object()

    monkeypatch.setattr(mongo_storage_monitor, "connect_postgres", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "close_postgres", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "connect_mongo", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "close_mongo", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "get_postgres_pool", pool_stub)
    monkeypatch.setattr(mongo_storage_monitor, "get_mongo_database", mongo_stub)
    monkeypatch.setattr(mongo_storage_monitor, "get_mongo_storage_ratio", ratio_stub)
    monkeypatch.setattr(
        mongo_storage_monitor,
        "prune_oldest_published_mongo_session",
        prune_stub,
    )
    monkeypatch.setattr(
        mongo_storage_monitor,
        "notify_developer",
        lambda **kwargs: calls.__setitem__("notify", calls["notify"] + 1),
    )

    result = await mongo_storage_monitor.run_monitor(check_only=False)
    assert calls["notify"] == 1
    assert calls["prune"] == 2
    assert prune_calls == [[], ["2024-01-01"]]
    assert result["pruned_dates"] == ["2024-01-01"]
    assert result["ratio"] == 0.85


@pytest.mark.asyncio
async def test_mongo_storage_monitor_continues_when_ratio_flat(monkeypatch):
    """Empty/no-progress date stays in pruned_dates; loop continues to next session."""
    calls = {"notify": 0}
    # Initial check 0.90; after empty date ratio flat; after real prune drop to target.
    ratios = iter([(1000, 0.90), (1000, 0.90), (700, 0.69)])
    pruned = iter(["2024-01-01", "2024-01-02"])
    prune_calls = []

    async def ratio_stub(conn, limit):
        del conn, limit
        return next(ratios)

    async def prune_stub(pool, conn, exclude_dates=None):
        del pool, conn
        prune_calls.append(list(exclude_dates or []))
        return next(pruned)

    async def pool_stub():
        return object()

    async def mongo_stub():
        return object()

    monkeypatch.setattr(mongo_storage_monitor, "connect_postgres", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "close_postgres", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "connect_mongo", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "close_mongo", _noop_async)
    monkeypatch.setattr(mongo_storage_monitor, "get_postgres_pool", pool_stub)
    monkeypatch.setattr(mongo_storage_monitor, "get_mongo_database", mongo_stub)
    monkeypatch.setattr(mongo_storage_monitor, "get_mongo_storage_ratio", ratio_stub)
    monkeypatch.setattr(
        mongo_storage_monitor,
        "prune_oldest_published_mongo_session",
        prune_stub,
    )
    monkeypatch.setattr(
        mongo_storage_monitor,
        "notify_developer",
        lambda **kwargs: calls.__setitem__("notify", calls["notify"] + 1),
    )

    result = await mongo_storage_monitor.run_monitor(check_only=False)
    assert calls["notify"] == 1
    assert result["pruned_dates"] == ["2024-01-01", "2024-01-02"]
    assert result["ratio"] == 0.69
    assert prune_calls == [[], ["2024-01-01"]]
