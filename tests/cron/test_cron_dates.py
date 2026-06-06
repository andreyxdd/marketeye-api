"""Tests for cron ingest date resolution."""

import pytest

from services.cron_dates import resolve_ingest_dates_for_market


@pytest.mark.asyncio
async def test_resolve_ingest_dates_includes_prior_when_missing(mongo_client, monkeypatch):
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
                "resolve_session_dates": lambda self, date: ("2024-06-03", "2024-05-31"),
            },
        )(),
    )

    dates = await resolve_ingest_dates_for_market(mongo_client, "US")
    assert dates == ["2024-06-03", "2024-05-31"]


@pytest.mark.asyncio
async def test_resolve_ingest_dates_skips_prior_when_complete(mongo_client, monkeypatch):
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
                "resolve_session_dates": lambda self, date: ("2024-06-03", "2024-05-31"),
            },
        )(),
    )

    dates = await resolve_ingest_dates_for_market(mongo_client, "US")
    assert dates == ["2024-06-03"]


@pytest.mark.asyncio
async def test_resolve_ingest_dates_raises_when_no_last_session(mongo_client, monkeypatch):
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
