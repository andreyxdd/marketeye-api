"""Tests for cron ingest date resolution."""

import threading
import types

import pytest

from services.cron_dates import (
    resolve_ingest_dates_for_market,
    unpublished_session_dates,
)


@pytest.mark.asyncio
async def test_resolve_ingest_dates_includes_prior_when_missing(
    mongo_client, monkeypatch
):
    async def fake_missing(conn, date, market="US"):
        del conn, market
        return ["AAPL"] if date == "2024-05-31" else []

    monkeypatch.setattr(
        "services.cron_dates.get_missing_tickers",
        fake_missing,
    )
    monkeypatch.setattr(
        "services.cron_dates.get_market_data_provider",
        lambda market="US": type(
            "StubProvider",
            (),
            {
                "resolve_session_dates": lambda self, date: (
                    "2024-06-03",
                    "2024-05-31",
                ),
            },
        )(),
    )

    dates = await resolve_ingest_dates_for_market(mongo_client, "US")
    assert dates == ["2024-06-03", "2024-05-31"]


@pytest.mark.asyncio
async def test_resolve_ingest_dates_skips_prior_when_complete(
    mongo_client, monkeypatch
):
    async def fake_missing(conn, date, market="US"):
        del conn, date, market
        return []

    monkeypatch.setattr(
        "services.cron_dates.get_missing_tickers",
        fake_missing,
    )
    monkeypatch.setattr(
        "services.cron_dates.get_market_data_provider",
        lambda market="US": type(
            "StubProvider",
            (),
            {
                "resolve_session_dates": lambda self, date: (
                    "2024-06-03",
                    "2024-05-31",
                ),
            },
        )(),
    )

    dates = await resolve_ingest_dates_for_market(mongo_client, "US")
    assert dates == ["2024-06-03"]


@pytest.mark.asyncio
async def test_resolve_ingest_dates_raises_when_no_last_session(
    mongo_client, monkeypatch
):
    monkeypatch.setattr(
        "services.cron_dates.get_market_data_provider",
        lambda market="US": type(
            "StubProvider",
            (),
            {
                "resolve_session_dates": lambda self, date: (None, None),
            },
        )(),
    )

    with pytest.raises(ValueError, match="LastCompletedSession"):
        await resolve_ingest_dates_for_market(mongo_client, "US")


def _thread_recording_provider(threads):
    def resolve_session_dates(date):
        del date
        threads.append(threading.current_thread())
        return ("2024-06-03", "2024-05-31")

    return types.SimpleNamespace(resolve_session_dates=resolve_session_dates)


@pytest.mark.asyncio
async def test_resolve_ingest_dates_probes_sessions_off_event_loop(monkeypatch):
    threads = []

    async def fake_missing(conn, date, market="US"):
        del conn, date, market
        return ["AAPL"]

    monkeypatch.setattr("services.cron_dates.get_missing_tickers", fake_missing)
    monkeypatch.setattr(
        "services.cron_dates.get_market_data_provider",
        lambda market="US": _thread_recording_provider(threads),
    )

    dates = await resolve_ingest_dates_for_market(None, "US")

    assert dates == ["2024-06-03", "2024-05-31"]
    assert len(threads) == 1
    assert threads[0] is not threading.main_thread()


@pytest.mark.asyncio
async def test_unpublished_session_dates_probes_sessions_off_event_loop(monkeypatch):
    threads = []

    async def fake_published(pool, date, market):
        del pool, market
        return date == "2024-05-31"

    monkeypatch.setattr("services.cron_dates.is_archive_complete", fake_published)
    monkeypatch.setattr(
        "services.cron_dates.get_market_data_provider",
        lambda market="US": _thread_recording_provider(threads),
    )

    dates = await unpublished_session_dates(None, "US")

    assert dates == ["2024-06-03"]
    assert len(threads) == 1
    assert threads[0] is not threading.main_thread()


@pytest.mark.asyncio
async def test_us_probe_requeues_until_bounce_complete_without_changing_to(monkeypatch):
    async def archive_complete(pool, date, market):
        del pool, date
        return market == "TO"

    monkeypatch.setattr("services.cron_dates.is_archive_complete", archive_complete)
    monkeypatch.setattr(
        "services.cron_dates.get_market_data_provider",
        lambda market: types.SimpleNamespace(
            resolve_session_dates=lambda date: ("2024-06-03", "2024-05-31")
        ),
    )

    assert await unpublished_session_dates(None, "US") == [
        "2024-05-31",
        "2024-06-03",
    ]
    assert await unpublished_session_dates(None, "TO") == []
