"""Publish gate requires tickers and US market_analytics artifact."""

import pytest

from db.crud.published_archive import (
    MARKET_ARTIFACT_KEY,
    is_session_published,
    truncate_published_tables,
    upsert_artifact,
    upsert_published_date,
    upsert_ticker_payload,
)


@pytest.fixture(autouse=True)
async def _clean_published_tables(postgres_pool):
    await truncate_published_tables(postgres_pool)
    yield
    await truncate_published_tables(postgres_pool)


@pytest.mark.asyncio
async def test_is_session_published_false_without_tickers(postgres_pool):
    await upsert_published_date(postgres_pool, "2024-06-03", market="US")
    await upsert_artifact(
        postgres_pool,
        "2024-06-03",
        MARKET_ARTIFACT_KEY,
        {"SP500": 5000.0},
        market="US",
    )

    assert not await is_session_published(postgres_pool, "2024-06-03", market="US")


@pytest.mark.asyncio
async def test_is_session_published_false_for_us_without_market_analytics(postgres_pool):
    await upsert_published_date(postgres_pool, "2024-06-03", market="US")
    await upsert_ticker_payload(
        postgres_pool,
        "2024-06-03",
        "AAPL",
        {"ticker": "AAPL"},
        market="US",
    )

    assert not await is_session_published(postgres_pool, "2024-06-03", market="US")


@pytest.mark.asyncio
async def test_is_session_published_true_for_complete_us_session(postgres_pool):
    await upsert_published_date(postgres_pool, "2024-06-03", market="US")
    await upsert_artifact(
        postgres_pool,
        "2024-06-03",
        MARKET_ARTIFACT_KEY,
        {"SP500": 5000.0},
        market="US",
    )
    await upsert_ticker_payload(
        postgres_pool,
        "2024-06-03",
        "AAPL",
        {"ticker": "AAPL"},
        market="US",
    )

    assert await is_session_published(postgres_pool, "2024-06-03", market="US")
