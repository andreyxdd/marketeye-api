"""Tests for published-session ingest gate."""

import pytest

from services.cron_dates import needs_ingest


@pytest.mark.asyncio
async def test_needs_ingest_false_when_last_and_prior_are_published(monkeypatch):
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

    async def published(pool, date, market):
        del pool, date, market
        return True

    monkeypatch.setattr("services.cron_dates.is_session_published", published)

    assert not await needs_ingest(object(), "US")


@pytest.mark.asyncio
async def test_needs_ingest_true_when_a_session_is_unpublished(monkeypatch):
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

    async def published(pool, date, market):
        del pool, market
        return date == "2024-06-03"

    monkeypatch.setattr("services.cron_dates.is_session_published", published)

    assert await needs_ingest(object(), "US")
