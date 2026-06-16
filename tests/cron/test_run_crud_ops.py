"""Tests for cronjob.run_crud_ops publish-before-delete gate."""

import pytest

import cronjob


async def _noop_async(*args, **kwargs):
    del args, kwargs
    return None


@pytest.mark.asyncio
async def test_run_crud_ops_happy_path(monkeypatch):
    calls = {
        "remove": [],
        "scrapes": 0,
    }

    async def remove_stub(conn, date, collection_name="analytics", market="US"):
        del conn
        calls["remove"].append((date, collection_name, market))

    async def remove_scrapes_stub(conn, date):
        del conn, date
        calls["scrapes"] += 1

    async def get_db_stub():
        return object()

    async def ingest_stub(conn, date, market="US"):
        del conn, date, market
        return "ingested"

    async def track_stub(conn, date, market="US"):
        del conn, date, market
        return "tracked"

    async def publish_stub(conn, pool, date, market="US"):
        del conn, pool, date, market
        return {"artifacts_written": 9, "tickers_written": 20}

    monkeypatch.setattr(cronjob, "connect_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "close_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "get_mongo_database", get_db_stub)
    monkeypatch.setattr(
        cronjob.analytics_service,
        "ingest_base_analytics_for_market",
        ingest_stub,
    )
    monkeypatch.setattr(cronjob, "put_top_tickers", track_stub)
    monkeypatch.setattr(cronjob.publish_service, "publish_day", publish_stub)
    monkeypatch.setattr(cronjob, "remove_base_analytics", remove_stub)
    monkeypatch.setattr(cronjob, "remove_scrapes", remove_scrapes_stub)
    monkeypatch.setattr(cronjob, "notify_developer", lambda **kwargs: None)

    message = await cronjob.run_crud_ops(
        "2024-06-03",
        "2024-03-04",
        "US",
        pg_pool=object(),
    )

    assert len(calls["remove"]) == 2
    assert ("2024-03-04", "analytics", "US") in calls["remove"]
    assert ("2024-03-04", "tracking", "US") in calls["remove"]
    assert calls["scrapes"] == 1
    assert "publish_service.publish_day: artifacts=9, tickers=20" in message


@pytest.mark.asyncio
async def test_run_crud_ops_publish_gate_skips_delete(monkeypatch):
    calls = {
        "remove": 0,
        "notified": 0,
    }

    async def remove_stub(conn, date, collection_name="analytics", market="US"):
        del conn, date, collection_name, market
        calls["remove"] += 1

    def notify_stub(**kwargs):
        del kwargs
        calls["notified"] += 1

    async def get_db_stub():
        return object()

    async def ingest_stub(conn, date, market="US"):
        del conn, date, market
        return "ingested"

    async def track_stub(conn, date, market="US"):
        del conn, date, market
        return "tracked"

    async def publish_fail_stub(conn, pool, date, market="US"):
        del conn, pool, date, market
        raise RuntimeError("publish failed")

    monkeypatch.setattr(cronjob, "connect_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "close_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "get_mongo_database", get_db_stub)
    monkeypatch.setattr(
        cronjob.analytics_service,
        "ingest_base_analytics_for_market",
        ingest_stub,
    )
    monkeypatch.setattr(cronjob, "put_top_tickers", track_stub)
    monkeypatch.setattr(cronjob.publish_service, "publish_day", publish_fail_stub)
    monkeypatch.setattr(cronjob, "remove_base_analytics", remove_stub)
    monkeypatch.setattr(cronjob, "remove_scrapes", _noop_async)
    monkeypatch.setattr(cronjob, "notify_developer", notify_stub)

    message = await cronjob.run_crud_ops(
        "2024-06-03",
        "2024-03-04",
        "US",
        pg_pool=object(),
    )

    assert calls["remove"] == 0
    assert calls["notified"] == 1
    assert "skipped remove_base_analytics" in message


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

    async def publish_stub(conn, pool, date, market="US"):
        del conn, pool, date, market
        calls["publish"] += 1
        return {"artifacts_written": 1, "tickers_written": 1}

    monkeypatch.setattr(cronjob, "connect_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "close_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "get_mongo_database", get_db_stub)
    monkeypatch.setattr(
        cronjob.analytics_service,
        "ingest_base_analytics_for_market",
        ingest_stub,
    )
    monkeypatch.setattr(cronjob, "put_top_tickers", track_stub)
    monkeypatch.setattr(cronjob.publish_service, "publish_day", publish_stub)
    monkeypatch.setattr(cronjob, "remove_base_analytics", _noop_async)
    monkeypatch.setattr(cronjob, "remove_scrapes", _noop_async)
    monkeypatch.setattr(
        cronjob,
        "notify_developer",
        lambda **kwargs: calls.__setitem__("notify", calls["notify"] + 1),
    )

    await cronjob.run_crud_ops("2024-06-03", "2024-03-04", "US", pg_pool=object())
    await cronjob.run_crud_ops("2024-06-03", "2024-03-04", "US", pg_pool=object())

    assert calls["publish"] == 2
    assert calls["notify"] == 0
