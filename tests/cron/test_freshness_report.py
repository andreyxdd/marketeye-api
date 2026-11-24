"""Tests for the production freshness report at the cron-date service seam."""

import types
from datetime import datetime

import pytest

from services import cron_dates


EXPECTED_SESSION = "2026-11-23"


def _provider():
    return types.SimpleNamespace(
        resolve_session_dates=lambda date, timeout_seconds=None: (
            EXPECTED_SESSION,
            "2026-11-20",
        )
    )


def _snapshot_v1(date):
    return {
        "schema_version": 1,
        "market": "US",
        "date": date,
        "rows": [
            {
                "ticker": "AAPL",
                "open": 100.0,
                "close": 101.0,
                "volume": 1000,
                "open_close_change_pct": 1.0,
                "bounce": [0.0] * 18,
            }
        ],
        "coverage": {
            "status": "exact",
            "universe_provenance": "test_fixture",
            "declared_universe_count": 1,
            "row_count": 1,
            "exclusions": [],
        },
    }


def _snapshot_v2(date):
    return {
        "schema_version": 2,
        "market": "US",
        "date": date,
        "max_lookback": 0,
        "rows": [],
        "coverage": {
            universe: {
                "status": "exact",
                "universe_provenance": "test_fixture",
                "exclusions_count": 0,
            }
            for universe in ("whole_market", "macd_history")
        },
    }


@pytest.mark.asyncio
async def test_freshness_report_is_fresh_when_all_expected_artifacts_are_valid(
    monkeypatch,
):
    async def archive_complete(pool, date, market):
        del pool
        return date == EXPECTED_SESSION and market in ("US", "TO")

    async def latest_published(pool, market):
        del pool, market
        return EXPECTED_SESSION

    async def artifact(pool, date, key, market="US"):
        del pool, market
        assert date == EXPECTED_SESSION
        if key == "stock_bounce:v1":
            return _snapshot_v1(date)
        if key == "stock_bounce:v2":
            return _snapshot_v2(date)
        raise AssertionError(f"unexpected artifact key: {key}")

    async def latest_artifact(pool, key, market="US"):
        del pool, key, market
        return EXPECTED_SESSION

    monkeypatch.setattr(cron_dates, "get_market_data_provider", lambda market: _provider())
    monkeypatch.setattr(cron_dates, "is_archive_complete", archive_complete)
    monkeypatch.setattr(cron_dates, "get_latest_published_date", latest_published)
    monkeypatch.setattr(cron_dates, "get_artifact_payload", artifact)
    monkeypatch.setattr(cron_dates, "get_latest_artifact_date", latest_artifact)

    report = await cron_dates.freshness_report(None)

    assert report["status"] == "fresh"
    assert report["markets"] == {
        "US": {
            "expected_session": EXPECTED_SESSION,
            "components": {
                "analytics": {"status": "fresh", "latest_session": EXPECTED_SESSION},
                "stock_bounce_v1": {
                    "status": "fresh",
                    "latest_session": EXPECTED_SESSION,
                },
                "stock_bounce_v2": {
                    "status": "fresh",
                    "latest_session": EXPECTED_SESSION,
                },
            },
        },
        "TO": {
            "expected_session": EXPECTED_SESSION,
            "components": {
                "analytics": {"status": "fresh", "latest_session": EXPECTED_SESSION}
            },
        },
    }
    checked_at = datetime.fromisoformat(report["checked_at"].replace("Z", "+00:00"))
    assert checked_at.tzinfo is not None
    assert report["checked_at"].endswith("Z")


@pytest.mark.asyncio
async def test_freshness_report_marks_provider_failure_unavailable_without_details(
    monkeypatch, caplog
):
    import logging

    import requests

    def fail_provider(date, timeout_seconds=None):
        del date, timeout_seconds
        raise requests.HTTPError(
            "429 for https://eodhd.test/api?api_token=private-token"
        )

    caplog.set_level(logging.ERROR, logger="services.cron_dates")
    monkeypatch.setattr(
        cron_dates,
        "get_market_data_provider",
        lambda market: types.SimpleNamespace(resolve_session_dates=fail_provider),
    )

    report = await cron_dates.freshness_report(None)

    assert report["status"] == "unavailable"
    assert report["markets"]["US"]["expected_session"] is None
    assert report["markets"]["TO"]["expected_session"] is None
    assert report["markets"]["US"]["components"] == {
        "analytics": {"status": "unavailable", "latest_session": None},
        "stock_bounce_v1": {"status": "unavailable", "latest_session": None},
        "stock_bounce_v2": {"status": "unavailable", "latest_session": None},
    }
    assert report["markets"]["TO"]["components"] == {
        "analytics": {"status": "unavailable", "latest_session": None}
    }
    assert "private-token" not in str(report)
    assert "private-token" not in caplog.text
    assert "HTTPError" in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.asyncio
async def test_freshness_report_contains_archive_lookup_failure_per_component(
    monkeypatch,
):
    async def archive_failure(pool, date, market):
        del pool, date, market
        raise RuntimeError("SELECT private_query_text")

    async def latest_published(pool, market):
        del pool, market
        return "2026-11-20"

    async def artifact(pool, date, key, market="US"):
        del pool, market
        return _snapshot_v1(date) if key == "stock_bounce:v1" else _snapshot_v2(date)

    async def latest_artifact(pool, key, market="US"):
        del pool, key, market
        return EXPECTED_SESSION

    monkeypatch.setattr(cron_dates, "get_market_data_provider", lambda market: _provider())
    monkeypatch.setattr(cron_dates, "is_archive_complete", archive_failure)
    monkeypatch.setattr(cron_dates, "get_latest_published_date", latest_published)
    monkeypatch.setattr(cron_dates, "get_artifact_payload", artifact)
    monkeypatch.setattr(cron_dates, "get_latest_artifact_date", latest_artifact)

    report = await cron_dates.freshness_report(None)

    assert report["status"] == "unavailable"
    for market in ("US", "TO"):
        analytics = report["markets"][market]["components"]["analytics"]
        assert analytics == {"status": "unavailable", "latest_session": None}
    assert report["markets"]["US"]["components"]["stock_bounce_v1"]["status"] == "fresh"
    assert report["markets"]["US"]["components"]["stock_bounce_v2"]["status"] == "fresh"
    assert "private_query_text" not in str(report)


@pytest.mark.asyncio
async def test_freshness_report_distinguishes_stale_and_malformed_artifacts(
    monkeypatch,
):
    async def archive_complete(pool, date, market):
        del pool, date
        return market == "TO"

    async def latest_published(pool, market):
        del pool
        return "2026-11-20" if market == "US" else EXPECTED_SESSION

    async def artifact(pool, date, key, market="US"):
        del pool, market
        assert date == EXPECTED_SESSION
        if key == "stock_bounce:v1":
            return {"schema_version": 1, "market": "US", "date": date, "rows": []}
        return _snapshot_v2("2026-11-20")

    async def latest_artifact(pool, key, market="US"):
        del pool, key, market
        return EXPECTED_SESSION

    monkeypatch.setattr(cron_dates, "get_market_data_provider", lambda market: _provider())
    monkeypatch.setattr(cron_dates, "is_archive_complete", archive_complete)
    monkeypatch.setattr(cron_dates, "get_latest_published_date", latest_published)
    monkeypatch.setattr(cron_dates, "get_artifact_payload", artifact)
    monkeypatch.setattr(cron_dates, "get_latest_artifact_date", latest_artifact)

    report = await cron_dates.freshness_report(None)

    assert report["status"] == "stale"
    assert report["markets"]["US"]["components"] == {
        "analytics": {"status": "stale", "latest_session": "2026-11-20"},
        "stock_bounce_v1": {"status": "stale", "latest_session": EXPECTED_SESSION},
        "stock_bounce_v2": {"status": "stale", "latest_session": EXPECTED_SESSION},
    }
    assert report["markets"]["TO"]["components"]["analytics"]["status"] == "fresh"


@pytest.mark.asyncio
async def test_freshness_report_probes_provider_off_event_loop(monkeypatch):
    import threading
    import time

    threads = []
    timeouts = []

    def slow_provider(date, timeout_seconds=None):
        del date
        threads.append(threading.current_thread())
        timeouts.append(timeout_seconds)
        time.sleep(0.05)
        return EXPECTED_SESSION, "2026-11-20"

    monkeypatch.setattr(cron_dates, "_PROVIDER_PROBE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        cron_dates,
        "get_market_data_provider",
        lambda market: types.SimpleNamespace(resolve_session_dates=slow_provider),
    )

    report = await cron_dates.freshness_report(None)

    assert report["status"] == "unavailable"
    assert threads
    assert all(thread is not threading.main_thread() for thread in threads)
    assert timeouts == [0.01, 0.01]


@pytest.mark.asyncio
async def test_freshness_report_reads_real_archive_artifacts(postgres_pool, monkeypatch):
    from db.crud.published_archive import (
        MARKET_ARTIFACT_KEY,
        STOCK_BOUNCE_ARTIFACT_KEY,
        STOCK_BOUNCE_V2_ARTIFACT_KEY,
        truncate_published_tables,
        upsert_artifact,
        upsert_ticker_payload,
    )

    await truncate_published_tables(postgres_pool)
    monkeypatch.setattr(cron_dates, "get_market_data_provider", lambda market: _provider())
    try:
        await upsert_ticker_payload(
            postgres_pool, EXPECTED_SESSION, "AAPL", {"ticker": "AAPL"}, market="US"
        )
        await upsert_artifact(
            postgres_pool,
            EXPECTED_SESSION,
            MARKET_ARTIFACT_KEY,
            {"SP500": 5000.0},
            market="US",
        )
        await upsert_artifact(
            postgres_pool,
            EXPECTED_SESSION,
            STOCK_BOUNCE_ARTIFACT_KEY,
            _snapshot_v1(EXPECTED_SESSION),
            market="US",
        )
        await upsert_artifact(
            postgres_pool,
            EXPECTED_SESSION,
            STOCK_BOUNCE_V2_ARTIFACT_KEY,
            _snapshot_v2(EXPECTED_SESSION),
            market="US",
        )
        await upsert_ticker_payload(
            postgres_pool, EXPECTED_SESSION, "SHOP", {"ticker": "SHOP"}, market="TO"
        )

        report = await cron_dates.freshness_report(postgres_pool)
    finally:
        await truncate_published_tables(postgres_pool)

    assert report["status"] == "fresh"
    assert report["markets"]["US"]["expected_session"] == EXPECTED_SESSION
    assert report["markets"]["TO"]["components"]["analytics"] == {
        "status": "fresh",
        "latest_session": EXPECTED_SESSION,
    }


@pytest.mark.asyncio
async def test_freshness_report_requests_bounded_provider_io(monkeypatch):
    timeouts = []

    def fail_after_recording_timeout(date, timeout_seconds=None):
        del date
        timeouts.append(timeout_seconds)
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        cron_dates,
        "get_market_data_provider",
        lambda market: types.SimpleNamespace(
            resolve_session_dates=fail_after_recording_timeout
        ),
    )

    report = await cron_dates.freshness_report(None)

    assert report["status"] == "unavailable"
    assert timeouts == [10.0, 10.0]


def test_eodhd_bounded_session_probe_times_out_http_and_does_not_retry_429(
    monkeypatch,
):
    import requests
    from providers.eodhd_to import EodhdTOProvider

    provider = EodhdTOProvider()
    calls = []
    response = requests.Response()
    response.status_code = 429
    response.url = "https://eodhd.test/api?api_token=private-token"

    def rate_limited(url, **kwargs):
        calls.append((url, kwargs))
        return response

    def sleep_unexpected(seconds):
        del seconds
        raise AssertionError("bounded freshness probe must not retry HTTP 429")

    monkeypatch.setattr(provider, "_http_get", rate_limited)
    monkeypatch.setattr("providers.eodhd_to.time.sleep", sleep_unexpected)

    with pytest.raises(requests.HTTPError):
        provider.resolve_session_dates("2026-11-24", timeout_seconds=0.25)

    assert len(calls) == 1
    assert calls[0][1] == {"timeout": 0.25}


@pytest.mark.asyncio
async def test_freshness_report_marks_only_overflowing_artifact_stale(monkeypatch):
    async def archive_complete(pool, date, market):
        del pool, date, market
        return True

    async def latest_published(pool, market):
        del pool, market
        return EXPECTED_SESSION

    async def artifact(pool, date, key, market="US"):
        del pool, market
        if key == "stock_bounce:v1":
            snapshot = _snapshot_v1(date)
            snapshot["rows"][0]["open"] = 10**10000
            return snapshot
        return _snapshot_v2(date)

    async def latest_artifact(pool, key, market="US"):
        del pool, key, market
        return EXPECTED_SESSION

    monkeypatch.setattr(cron_dates, "get_market_data_provider", lambda market: _provider())
    monkeypatch.setattr(cron_dates, "is_archive_complete", archive_complete)
    monkeypatch.setattr(cron_dates, "get_latest_published_date", latest_published)
    monkeypatch.setattr(cron_dates, "get_artifact_payload", artifact)
    monkeypatch.setattr(cron_dates, "get_latest_artifact_date", latest_artifact)

    report = await cron_dates.freshness_report(None)

    assert report["status"] == "stale"
    assert report["markets"]["US"]["components"]["stock_bounce_v1"] == {
        "status": "stale",
        "latest_session": EXPECTED_SESSION,
    }
    assert report["markets"]["US"]["components"]["stock_bounce_v2"]["status"] == "fresh"
    assert report["markets"]["TO"]["components"]["analytics"]["status"] == "fresh"
