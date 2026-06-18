"""Tests for cronjob failure tracking and non-zero exit semantics."""

import pytest

import cronjob


async def _noop_async(*args, **kwargs):
    del args, kwargs
    return None


@pytest.fixture(autouse=True)
def _reset_cron_failed():
    cronjob.reset_cron_failed()
    yield
    cronjob.reset_cron_failed()


@pytest.mark.asyncio
async def test_cronjob_sets_failed_flag_on_run_crud_ops_error(monkeypatch):
    async def resolve_dates_stub(conn, market):
        del conn
        return ["2024-06-03"]

    async def run_crud_fail(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("AtlasError quota exceeded")

    notified = []

    def notify_stub(**kwargs):
        notified.append(kwargs)

    monkeypatch.setattr(cronjob, "connect_postgres", _noop_async)
    monkeypatch.setattr(cronjob, "close_postgres", _noop_async)
    monkeypatch.setattr(cronjob, "get_postgres_pool", _noop_async)
    monkeypatch.setattr(cronjob, "connect_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "close_mongo", _noop_async)
    monkeypatch.setattr(cronjob, "get_mongo_database", _noop_async)
    monkeypatch.setattr(cronjob.mongo_storage_monitor, "run_monitor", _noop_async)
    monkeypatch.setattr(cronjob, "resolve_ingest_dates_for_market", resolve_dates_stub)
    monkeypatch.setattr(cronjob, "run_crud_ops", run_crud_fail)
    monkeypatch.setattr(cronjob, "notify_developer", notify_stub)
    monkeypatch.setattr(cronjob, "clear_ticker_universe_cache", lambda: None)

    await cronjob.cronjob(markets=["US"])

    assert cronjob.cron_failed() is True
    assert len(notified) == 1
    assert "AtlasError" in notified[0]["body"] or "quota" in notified[0]["body"]


@pytest.mark.asyncio
async def test_run_explicit_dates_sets_failed_flag_on_error(monkeypatch):
    async def run_crud_fail(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("AtlasError quota exceeded")

    notified = []

    def notify_stub(**kwargs):
        notified.append(kwargs)

    monkeypatch.setattr(cronjob, "connect_postgres", _noop_async)
    monkeypatch.setattr(cronjob, "close_postgres", _noop_async)
    monkeypatch.setattr(cronjob, "get_postgres_pool", _noop_async)
    monkeypatch.setattr(cronjob, "run_crud_ops", run_crud_fail)
    monkeypatch.setattr(cronjob, "notify_developer", notify_stub)

    await cronjob.run_explicit_dates(["2024-06-03"], markets=["US"])

    assert cronjob.cron_failed() is True
    assert len(notified) == 1


def test_main_exits_nonzero_when_cron_failed(monkeypatch):
    exit_codes = []

    def exit_stub(code=0):
        exit_codes.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(cronjob.asyncio, "run", lambda coro: None)
    monkeypatch.setattr(cronjob, "cron_failed", lambda: True)
    monkeypatch.setattr(cronjob.sys, "exit", exit_stub)
    monkeypatch.setattr(
        cronjob,
        "_parse_args",
        lambda: type("Args", (), {"dates": [], "markets": None})(),
    )

    with pytest.raises(SystemExit) as exc_info:
        cronjob.main()

    assert exc_info.value.code == 1
    assert exit_codes == [1]
