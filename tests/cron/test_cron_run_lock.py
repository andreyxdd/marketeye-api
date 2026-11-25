"""Tests for the single-run advisory lock around cronjob.main()."""

import asyncio

import pytest

import cronjob


class _FakeLockConn:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


def _args(dates):
    return lambda: type("Args", (), {"dates": dates, "markets": None})()


@pytest.fixture(autouse=True)
def _reset_cron_failed():
    cronjob.reset_cron_failed()
    yield
    cronjob.reset_cron_failed()


@pytest.fixture(autouse=True)
def _private_loop_run(monkeypatch):
    """Run main()'s coroutine on a private loop.

    Real asyncio.run() clears the global loop and breaks the session-scoped
    pytest-asyncio loop for later tests.
    """

    def run(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(cronjob.asyncio, "run", run)


@pytest.mark.parametrize("dates", [[], ["2024-06-03"]])
def test_main_held_lock_prints_busy_and_skips_ingest(monkeypatch, capsys, dates):
    calls = []

    async def held():
        return None

    async def ingest_unexpected(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(cronjob, "acquire_run_lock", held)
    monkeypatch.setattr(cronjob, "cronjob", ingest_unexpected)
    monkeypatch.setattr(cronjob, "run_explicit_dates", ingest_unexpected)
    monkeypatch.setattr(cronjob, "_parse_args", _args(dates))

    cronjob.main()  # returns normally: exit code 0

    assert calls == []
    assert "cron busy: another run holds the lock" in capsys.readouterr().out


@pytest.mark.parametrize(
    "dates, expected",
    [([], "cronjob"), (["2024-06-03"], "run_explicit_dates")],
)
def test_main_free_lock_runs_ingest_and_releases(monkeypatch, dates, expected):
    calls = []
    conn = _FakeLockConn()

    async def free():
        return conn

    async def cronjob_stub(*args, **kwargs):
        assert not conn.closed, "lock must be held during the run"
        calls.append("cronjob")

    async def explicit_stub(*args, **kwargs):
        assert not conn.closed, "lock must be held during the run"
        calls.append("run_explicit_dates")

    monkeypatch.setattr(cronjob, "acquire_run_lock", free)
    monkeypatch.setattr(cronjob, "cronjob", cronjob_stub)
    monkeypatch.setattr(cronjob, "run_explicit_dates", explicit_stub)
    monkeypatch.setattr(cronjob, "_parse_args", _args(dates))

    cronjob.main()

    assert calls == [expected]
    assert conn.closed


def test_main_releases_lock_when_run_raises(monkeypatch):
    conn = _FakeLockConn()

    async def free():
        return conn

    async def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cronjob, "acquire_run_lock", free)
    monkeypatch.setattr(cronjob, "cronjob", boom)
    monkeypatch.setattr(cronjob, "_parse_args", _args([]))

    with pytest.raises(RuntimeError):
        cronjob.main()

    assert conn.closed


def test_main_lock_error_alerts_and_exits_nonzero(monkeypatch):
    calls = []
    notified = []

    async def lock_error():
        raise OSError("connection refused")

    async def ingest_unexpected(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(cronjob, "acquire_run_lock", lock_error)
    monkeypatch.setattr(cronjob, "cronjob", ingest_unexpected)
    monkeypatch.setattr(cronjob, "run_explicit_dates", ingest_unexpected)
    monkeypatch.setattr(cronjob, "notify_developer", lambda **kw: notified.append(kw))
    monkeypatch.setattr(cronjob, "_parse_args", _args([]))

    with pytest.raises(SystemExit) as exc_info:
        cronjob.main()

    assert exc_info.value.code == 1
    assert cronjob.cron_failed() is True
    assert calls == []
    assert "connection refused" in notified[0]["body"]
