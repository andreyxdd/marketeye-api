"""Tests for reproducible per-phase cron timings."""

import pytest

import cronjob


@pytest.mark.asyncio
async def test_finalize_cron_run_prints_recorded_phase_timings(monkeypatch, capsys):
    report = cronjob.CronRunReport()
    report.record_timing("US", "2026-11-23", "prune", 1.25)
    monkeypatch.setattr(cronjob, "time", lambda: 12.0)

    await cronjob._finalize_cron_run(report, 10.0, [])

    output = capsys.readouterr().out
    assert "Analytics cronjob finished on 2.0 seconds" in output
    assert "Phase timings (seconds):" in output
    assert "- US 2026-11-23 [prune]: 1.25s" in output


@pytest.mark.asyncio
async def test_run_crud_ops_records_every_attempted_phase_duration(monkeypatch):
    async def noop(*args, **kwargs):
        del args, kwargs

    async def get_db():
        return object()

    async def archive_complete(pool, date, market):
        del pool, date, market
        return True

    async def ingest(conn, date, market="US"):
        del conn, date, market
        return "ingested"

    async def track(conn, date, market="US"):
        del conn, date, market
        return "tracked"

    async def tickers(conn, date, market="US"):
        del conn, date, market
        return ["AAPL"]

    async def publish(conn, pool, date, market="US", include_mentions=False):
        del conn, pool, date, market, include_mentions
        return {"artifacts_written": 2, "tickers_written": 1}

    monkeypatch.setattr(cronjob, "connect_mongo", noop)
    monkeypatch.setattr(cronjob, "close_mongo", noop)
    monkeypatch.setattr(cronjob, "get_mongo_database", get_db)
    monkeypatch.setattr(cronjob, "is_archive_complete", archive_complete)
    monkeypatch.setattr(cronjob, "prune_mongo_session_date", noop)
    monkeypatch.setattr(
        cronjob.analytics_service, "ingest_base_analytics_for_market", ingest
    )
    monkeypatch.setattr(cronjob, "put_top_tickers", track)
    monkeypatch.setattr(cronjob, "get_analytics_tickers", tickers)
    monkeypatch.setattr(cronjob.publish_service, "publish_day", publish)
    monkeypatch.setattr(
        cronjob, "time", iter([10.0, 11.25, 20.0, 22.5, 30.0, 30.75, 40.0, 42.0]).__next__
    )
    report = cronjob.CronRunReport()

    await cronjob.run_crud_ops(
        "2026-11-23", "2026-09-01", "US", pg_pool=object(), report=report
    )

    assert [(item.phase, item.elapsed_seconds) for item in report.timings] == [
        ("prune", 1.25),
        ("ingest", 2.5),
        ("track", 0.75),
        ("publish", 2.0),
    ]
    assert not report.has_errors()


@pytest.mark.asyncio
async def test_run_crud_ops_records_failed_ingest_duration_without_publish(
    monkeypatch,
):
    async def noop(*args, **kwargs):
        del args, kwargs

    async def get_db():
        return object()

    async def archive_incomplete(pool, date, market):
        del pool, date, market
        return False

    async def ingest_failure(conn, date, market="US"):
        del conn, date, market
        raise RuntimeError("ingest failed")

    async def publish_unexpected(*args, **kwargs):
        del args, kwargs
        raise AssertionError("failed ingest must not publish")

    monkeypatch.setattr(cronjob, "connect_mongo", noop)
    monkeypatch.setattr(cronjob, "close_mongo", noop)
    monkeypatch.setattr(cronjob, "get_mongo_database", get_db)
    monkeypatch.setattr(cronjob, "is_archive_complete", archive_incomplete)
    monkeypatch.setattr(
        cronjob.analytics_service, "ingest_base_analytics_for_market", ingest_failure
    )
    monkeypatch.setattr(cronjob.publish_service, "publish_day", publish_unexpected)
    monkeypatch.setattr(cronjob, "notify_developer", lambda **kwargs: None)
    monkeypatch.setattr(cronjob, "time", iter([5.0, 6.5]).__next__)
    report = cronjob.CronRunReport()

    await cronjob.run_crud_ops(
        "2026-11-23", "2026-09-01", "US", pg_pool=object(), report=report
    )

    assert [(item.phase, item.elapsed_seconds) for item in report.timings] == [
        ("ingest", 1.5)
    ]
    assert [item.phase for item in report.errors] == ["ingest"]
