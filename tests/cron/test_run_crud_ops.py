"""Tests for cronjob.run_crud_ops publish-before-delete gate."""

import pytest

import cronjob


async def _noop_async(*args, **kwargs):
    del args, kwargs
    return None


@pytest.mark.asyncio
async def test_run_crud_ops_happy_path(monkeypatch):
    calls = {
        "order": [],
        "prune": [],
        "publish_kwargs": [],
    }

    async def published_stub(pool, date, market):
        del pool
        return date == "2024-03-04" and market == "US"

    async def prune_stub(conn, date, market):
        del conn
        calls["order"].append("prune")
        calls["prune"].append((date, market))

    async def get_db_stub():
        return object()

    async def ingest_stub(conn, date, market="US"):
        del conn, date, market
        calls["order"].append("ingest")
        return "ingested"

    async def track_stub(conn, date, market="US"):
        del conn, date, market
        calls["order"].append("track")
        return "tracked"

    async def publish_stub(conn, pool, date, market="US", include_mentions=True):
        del conn, pool, date, market
        calls["order"].append("publish")
        calls["publish_kwargs"].append(include_mentions)
        return {"artifacts_written": 9, "tickers_written": 20}

    monkeypatch.setattr(cronjob, "connect_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "close_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "get_mongo_database", get_db_stub)
    monkeypatch.setattr(cronjob, "is_session_published", published_stub)
    monkeypatch.setattr(cronjob, "prune_mongo_session_date", prune_stub)
    monkeypatch.setattr(
        cronjob.analytics_service,
        "ingest_base_analytics_for_market",
        ingest_stub,
    )
    monkeypatch.setattr(cronjob, "put_top_tickers", track_stub)
    monkeypatch.setattr(cronjob.publish_service, "publish_day", publish_stub)
    monkeypatch.setattr(cronjob, "notify_developer", lambda **kwargs: None)

    message = await cronjob.run_crud_ops(
        "2024-06-03",
        "2024-03-04",
        "US",
        pg_pool=object(),
    )

    assert calls["order"] == ["prune", "ingest", "track", "publish"]
    assert calls["prune"] == [("2024-03-04", "US")]
    assert calls["publish_kwargs"] == [False]
    assert "publish_service.publish_day: artifacts=9, tickers=20" in message


@pytest.mark.asyncio
async def test_run_crud_ops_publish_gate_skips_delete(monkeypatch):
    calls = {
        "order": [],
        "pruned": 0,
        "notified": 0,
    }

    async def published_stub(pool, date, market):
        del pool
        return date == "2024-03-04" and market == "US"

    async def prune_stub(conn, date, market):
        del conn, date, market
        calls["order"].append("prune")
        calls["pruned"] += 1

    def notify_stub(**kwargs):
        del kwargs
        calls["notified"] += 1

    async def get_db_stub():
        return object()

    async def ingest_stub(conn, date, market="US"):
        del conn, date, market
        calls["order"].append("ingest")
        return "ingested"

    async def track_stub(conn, date, market="US"):
        del conn, date, market
        calls["order"].append("track")
        return "tracked"

    async def publish_fail_stub(conn, pool, date, market="US", include_mentions=True):
        del conn, pool, date, market, include_mentions
        calls["order"].append("publish")
        raise RuntimeError("publish failed")

    monkeypatch.setattr(cronjob, "connect_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "close_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "get_mongo_database", get_db_stub)
    monkeypatch.setattr(cronjob, "is_session_published", published_stub)
    monkeypatch.setattr(cronjob, "prune_mongo_session_date", prune_stub)
    monkeypatch.setattr(
        cronjob.analytics_service,
        "ingest_base_analytics_for_market",
        ingest_stub,
    )
    monkeypatch.setattr(cronjob, "put_top_tickers", track_stub)
    monkeypatch.setattr(cronjob.publish_service, "publish_day", publish_fail_stub)
    monkeypatch.setattr(cronjob, "notify_developer", notify_stub)

    message = await cronjob.run_crud_ops(
        "2024-06-03",
        "2024-03-04",
        "US",
        pg_pool=object(),
    )

    assert calls["order"] == ["prune", "ingest", "track", "publish"]
    assert calls["pruned"] == 1
    assert calls["notified"] == 1
    assert "publish_service.publish_day failed" in message
    assert "skipped remove_base_analytics" not in message


@pytest.mark.asyncio
async def test_run_crud_ops_idempotent_when_repeated(monkeypatch):
    calls = {
        "publish": 0,
        "notify": 0,
    }

    async def get_db_stub():
        return object()

    async def ingest_stub(conn, date, market="US"):
        del conn, date, market
        return "ingested"

    async def track_stub(conn, date, market="US"):
        del conn, date, market
        return "tracked"

    async def publish_stub(conn, pool, date, market="US", include_mentions=True):
        del conn, pool, date, market, include_mentions
        calls["publish"] += 1
        return {"artifacts_written": 1, "tickers_written": 1}

    monkeypatch.setattr(cronjob, "connect_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "close_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "get_mongo_database", get_db_stub)
    monkeypatch.setattr(cronjob, "is_session_published", _noop_async)
    monkeypatch.setattr(cronjob, "prune_mongo_session_date", _noop_async)
    monkeypatch.setattr(
        cronjob.analytics_service,
        "ingest_base_analytics_for_market",
        ingest_stub,
    )
    monkeypatch.setattr(cronjob, "put_top_tickers", track_stub)
    monkeypatch.setattr(cronjob.publish_service, "publish_day", publish_stub)
    monkeypatch.setattr(
        cronjob,
        "notify_developer",
        lambda **kwargs: calls.__setitem__("notify", calls["notify"] + 1),
    )

    await cronjob.run_crud_ops("2024-06-03", "2024-03-04", "US", pg_pool=object())
    await cronjob.run_crud_ops("2024-06-03", "2024-03-04", "US", pg_pool=object())

    assert calls["publish"] == 2
    assert calls["notify"] == 0
