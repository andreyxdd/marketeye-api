"""Cron partial-failure isolation tests."""

import asyncpg
import pytest

import cronjob


async def _noop_async(*args, **kwargs):
    del args, kwargs
    return None


async def _tickers_stub(conn, date, market="US"):
    del conn, date, market
    return ["AAPL"]


@pytest.mark.asyncio
async def test_cronjob_continues_after_run_crud_ops_failure(monkeypatch):
    calls = []

    async def unpublished_dates_stub(pool, market):
        del pool, market
        return ["2024-06-03"]

    async def run_crud_stub(
        date_to_insert,
        date_to_remove,
        market,
        pg_pool=None,
        report=None,
    ):
        del date_to_insert, date_to_remove, pg_pool, report
        calls.append(market)
        if market == "US":
            raise RuntimeError("US failed")
        return "ok"

    monkeypatch.setattr(cronjob, "connect_postgres", _noop_async)
    monkeypatch.setattr(cronjob, "close_postgres", _noop_async)
    monkeypatch.setattr(cronjob, "get_postgres_pool", _noop_async)
    monkeypatch.setattr(cronjob, "connect_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "close_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "get_mongo_database", _noop_async)
    monkeypatch.setattr(cronjob.mongo_storage_monitor, "run_monitor", _noop_async)
    monkeypatch.setattr(cronjob, "unpublished_session_dates", unpublished_dates_stub)
    monkeypatch.setattr(cronjob, "run_crud_ops", run_crud_stub)
    monkeypatch.setattr(cronjob, "notify_developer", lambda **kwargs: None)
    monkeypatch.setattr(cronjob, "clear_ticker_universe_cache", lambda: None)

    cronjob.reset_cron_failed()
    await cronjob.cronjob(markets=["US", "TO"])

    assert calls == ["US", "TO"]
    assert cronjob.cron_failed() is True


@pytest.mark.asyncio
async def test_run_crud_ops_ingest_failure_skips_publish(monkeypatch):
    report = cronjob.CronRunReport()

    async def get_db_stub():
        return object()

    async def ingest_fail(conn, date, market="US"):
        del conn, date, market
        raise RuntimeError("ingest failed")

    monkeypatch.setattr(cronjob, "connect_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "close_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "get_mongo_database", get_db_stub)
    monkeypatch.setattr(cronjob, "is_archive_complete", _noop_async)
    monkeypatch.setattr(
        cronjob.analytics_service,
        "ingest_base_analytics_for_market",
        ingest_fail,
    )
    publish_called = {"value": False}

    async def publish_stub(*args, **kwargs):
        del args, kwargs
        publish_called["value"] = True
        return {"artifacts_written": 0, "tickers_written": 0}

    monkeypatch.setattr(cronjob.publish_service, "publish_day", publish_stub)
    monkeypatch.setattr(cronjob, "notify_developer", lambda **kwargs: None)

    message = await cronjob.run_crud_ops(
        "2024-06-03",
        "2024-03-04",
        "US",
        pg_pool=object(),
        report=report,
    )

    assert publish_called["value"] is False
    assert report.has_errors()
    assert "ingest" in message or message == ""


@pytest.mark.asyncio
async def test_run_crud_ops_publish_failure_keeps_ingest_message(monkeypatch):
    report = cronjob.CronRunReport()
    calls = _stub_publish_deps(monkeypatch, [RuntimeError("publish failed")])

    message = await _run_us(report)

    assert calls["publish"] == 1
    assert "ingested" in message
    assert "tracked" in message
    assert "publish_service.publish_day failed" in message
    assert report.has_errors()


def _stub_publish_deps(monkeypatch, publish_errors):
    """Stub run_crud_ops deps; publish_day raises each error in turn, then succeeds."""
    calls = {"publish": 0}

    async def get_db_stub():
        return object()

    async def ingest_stub(conn, date, market="US"):
        del conn, date, market
        return "ingested"

    async def track_stub(conn, date, market="US"):
        del conn, date, market
        return "tracked"

    async def publish_stub(conn, pool, date, market="US", include_mentions=False):
        del conn, pool, date, market, include_mentions
        calls["publish"] += 1
        if calls["publish"] <= len(publish_errors):
            raise publish_errors[calls["publish"] - 1]
        return {"artifacts_written": 2, "tickers_written": 1}

    monkeypatch.setattr(cronjob, "connect_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "close_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "get_mongo_database", get_db_stub)
    monkeypatch.setattr(cronjob, "is_archive_complete", _noop_async)
    monkeypatch.setattr(cronjob, "get_analytics_tickers", _tickers_stub)
    monkeypatch.setattr(
        cronjob.analytics_service,
        "ingest_base_analytics_for_market",
        ingest_stub,
    )
    monkeypatch.setattr(cronjob, "put_top_tickers", track_stub)
    monkeypatch.setattr(cronjob.publish_service, "publish_day", publish_stub)
    monkeypatch.setattr(cronjob, "notify_developer", lambda **kwargs: None)
    return calls


async def _run_us(report):
    return await cronjob.run_crud_ops(
        "2024-06-03",
        "2024-03-04",
        "US",
        pg_pool=object(),
        report=report,
    )


@pytest.mark.asyncio
async def test_run_crud_ops_publish_retries_once_on_connection_error(monkeypatch):
    report = cronjob.CronRunReport()
    calls = _stub_publish_deps(
        monkeypatch,
        [asyncpg.ConnectionDoesNotExistError("connection was closed")],
    )

    message = await _run_us(report)

    assert calls["publish"] == 2
    assert not report.has_errors()
    assert "publish_service.publish_day: artifacts=2, tickers=1" in message


@pytest.mark.asyncio
async def test_run_crud_ops_publish_records_one_error_when_retry_fails(monkeypatch):
    report = cronjob.CronRunReport()
    calls = _stub_publish_deps(
        monkeypatch,
        [
            asyncpg.ConnectionDoesNotExistError("connection was closed"),
            asyncpg.ConnectionDoesNotExistError("connection was closed"),
        ],
    )

    message = await _run_us(report)

    assert calls["publish"] == 2
    assert [e.phase for e in report.errors] == ["publish"]
    assert "publish_service.publish_day failed" in message
