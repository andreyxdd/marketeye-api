"""TO tracking-density floor after put_top_tickers."""

import pytest

from core.settings import MONGO_DB_NAME
from db.crud import tracking
import cronjob


@pytest.mark.asyncio
async def test_count_prior_unbanded_sessions_uses_frequency_window(monkeypatch):
    """Nine prior unbanded docs in window → count 9 (independent of ticker membership)."""
    queries = []

    class TrackingCollectionStub:
        async def count_documents(self, query):
            queries.append(query)
            return 9

    class MarketDbStub:
        def __getitem__(self, collection_name):
            if collection_name == tracking.MONGO_TRACKING_COLLECTION:
                return TrackingCollectionStub()
            raise KeyError(collection_name)

    conn = {MONGO_DB_NAME: MarketDbStub()}
    monkeypatch.setattr(tracking, "get_past_date", lambda period, date: "2024-05-09")
    monkeypatch.setattr(
        tracking,
        "get_epoch",
        lambda date: 1000 if date == "2024-05-09" else 2000,
    )

    count = await tracking.count_prior_unbanded_tracking_sessions(
        conn,
        "2024-06-03",
        criterion="one_day_avg_mf",
        period=25,
        market="TO",
    )

    assert count == 9
    assert queries, "expected count_documents call"
    query = queries[0]
    assert query["date"] == {"$gt": 1000, "$lt": 2000}
    assert query["criterion"] == "one_day_avg_mf"
    assert {"market": "TO"} in query["$and"]
    assert {
        "$or": [
            {"price_band": None},
            {"price_band": {"$exists": False}},
        ]
    } in query["$and"]


@pytest.mark.asyncio
async def test_run_crud_ops_to_below_density_floor_records_failure(monkeypatch):
    calls = {"notified": 0, "publish": 0}

    async def get_db_stub():
        return object()

    async def ingest_stub(conn, date, market="US"):
        del conn, date, market
        return "ingested"

    async def track_stub(conn, date, market="US"):
        del conn, date, market
        return "tracked"

    async def density_stub(conn, date, criterion="one_day_avg_mf", period=25, market="US"):
        del conn, date, criterion, period, market
        return 2  # RCA symptom: two prior sessions

    async def publish_stub(conn, pool, date, market="US", include_mentions=True):
        del conn, pool, date, market, include_mentions
        calls["publish"] += 1
        return {"artifacts_written": 1, "tickers_written": 1}

    async def tickers_stub(conn, date, market="US"):
        del conn, date, market
        return ["RY.TO"]

    monkeypatch.setattr(cronjob, "connect_mongo", lambda: _async_noop())
    monkeypatch.setattr(cronjob, "close_mongo", lambda: _async_noop())
    monkeypatch.setattr(cronjob, "get_mongo_database", get_db_stub)
    monkeypatch.setattr(cronjob, "is_archive_complete", lambda *a, **k: _async_return(False))
    monkeypatch.setattr(cronjob, "prune_mongo_session_date", lambda *a, **k: _async_noop())
    monkeypatch.setattr(cronjob, "get_analytics_tickers", tickers_stub)
    monkeypatch.setattr(
        cronjob.analytics_service,
        "ingest_base_analytics_for_market",
        ingest_stub,
    )
    monkeypatch.setattr(cronjob, "put_top_tickers", track_stub)
    monkeypatch.setattr(
        cronjob, "count_prior_unbanded_tracking_sessions", density_stub
    )
    monkeypatch.setattr(cronjob.publish_service, "publish_day", publish_stub)
    monkeypatch.setattr(
        cronjob,
        "notify_developer",
        lambda **kwargs: calls.__setitem__("notified", calls["notified"] + 1),
    )
    cronjob.reset_cron_failed()

    report = cronjob.CronRunReport()
    await cronjob.run_crud_ops(
        "2024-06-03",
        "2024-03-04",
        "TO",
        pg_pool=object(),
        report=report,
    )

    assert report.has_errors()
    phases = [e.phase for e in report.errors]
    assert "track_density" in phases
    density_err = next(e for e in report.errors if e.phase == "track_density")
    assert density_err.market == "TO"
    assert "2" in density_err.error
    assert str(cronjob.TO_TRACKING_DENSITY_FLOOR) in density_err.error
    assert cronjob.cron_failed()
    assert calls["notified"] >= 1
    # Density fail must not publish blank Frequencies artifacts.
    assert calls["publish"] == 0


@pytest.mark.asyncio
async def test_run_crud_ops_to_at_density_floor_no_density_error(monkeypatch):
    calls = {"publish": 0}

    async def get_db_stub():
        return object()

    async def ingest_stub(conn, date, market="US"):
        del conn, date, market
        return "ingested"

    async def track_stub(conn, date, market="US"):
        del conn, date, market
        return "tracked"

    async def density_stub(conn, date, criterion="one_day_avg_mf", period=25, market="US"):
        del conn, date, criterion, period, market
        return 10

    async def publish_stub(conn, pool, date, market="US", include_mentions=True):
        del conn, pool, date, market, include_mentions
        calls["publish"] += 1
        return {"artifacts_written": 1, "tickers_written": 1}

    async def tickers_stub(conn, date, market="US"):
        del conn, date, market
        return ["RY.TO"]

    monkeypatch.setattr(cronjob, "connect_mongo", lambda: _async_noop())
    monkeypatch.setattr(cronjob, "close_mongo", lambda: _async_noop())
    monkeypatch.setattr(cronjob, "get_mongo_database", get_db_stub)
    monkeypatch.setattr(cronjob, "is_archive_complete", lambda *a, **k: _async_return(False))
    monkeypatch.setattr(cronjob, "prune_mongo_session_date", lambda *a, **k: _async_noop())
    monkeypatch.setattr(cronjob, "get_analytics_tickers", tickers_stub)
    monkeypatch.setattr(
        cronjob.analytics_service,
        "ingest_base_analytics_for_market",
        ingest_stub,
    )
    monkeypatch.setattr(cronjob, "put_top_tickers", track_stub)
    monkeypatch.setattr(
        cronjob, "count_prior_unbanded_tracking_sessions", density_stub
    )
    monkeypatch.setattr(cronjob.publish_service, "publish_day", publish_stub)
    monkeypatch.setattr(cronjob, "notify_developer", lambda **kwargs: None)
    cronjob.reset_cron_failed()

    report = cronjob.CronRunReport()
    await cronjob.run_crud_ops(
        "2024-06-03",
        "2024-03-04",
        "TO",
        pg_pool=object(),
        report=report,
    )

    assert not any(e.phase == "track_density" for e in report.errors)
    assert not report.has_errors()
    assert calls["publish"] == 1


@pytest.mark.asyncio
async def test_run_crud_ops_us_skips_density_guard(monkeypatch):
    density_calls = []

    async def get_db_stub():
        return object()

    async def ingest_stub(conn, date, market="US"):
        del conn, date, market
        return "ingested"

    async def track_stub(conn, date, market="US"):
        del conn, date, market
        return "tracked"

    async def density_stub(conn, date, criterion="one_day_avg_mf", period=25, market="US"):
        density_calls.append((date, market))
        return 0

    async def publish_stub(conn, pool, date, market="US", include_mentions=True):
        del conn, pool, date, market, include_mentions
        return {"artifacts_written": 1, "tickers_written": 1}

    async def tickers_stub(conn, date, market="US"):
        del conn, date, market
        return ["AAPL"]

    monkeypatch.setattr(cronjob, "connect_mongo", lambda: _async_noop())
    monkeypatch.setattr(cronjob, "close_mongo", lambda: _async_noop())
    monkeypatch.setattr(cronjob, "get_mongo_database", get_db_stub)
    monkeypatch.setattr(cronjob, "is_archive_complete", lambda *a, **k: _async_return(False))
    monkeypatch.setattr(cronjob, "prune_mongo_session_date", lambda *a, **k: _async_noop())
    monkeypatch.setattr(cronjob, "get_analytics_tickers", tickers_stub)
    monkeypatch.setattr(
        cronjob.analytics_service,
        "ingest_base_analytics_for_market",
        ingest_stub,
    )
    monkeypatch.setattr(cronjob, "put_top_tickers", track_stub)
    monkeypatch.setattr(
        cronjob, "count_prior_unbanded_tracking_sessions", density_stub
    )
    monkeypatch.setattr(cronjob.publish_service, "publish_day", publish_stub)
    monkeypatch.setattr(cronjob, "notify_developer", lambda **kwargs: None)
    cronjob.reset_cron_failed()

    report = cronjob.CronRunReport()
    await cronjob.run_crud_ops(
        "2024-06-03",
        "2024-03-04",
        "US",
        pg_pool=object(),
        report=report,
    )

    assert density_calls == []
    assert not report.has_errors()


async def _async_noop():
    return None


async def _async_return(value):
    return value
