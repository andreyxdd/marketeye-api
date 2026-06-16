"""E2e cold-path reads from PostgreSQL archive."""

import pytest

from db.crud.published_archive import (
    MARKET_ARTIFACT_KEY,
    build_criterion_artifact_key,
    build_lists_artifact_key,
    upsert_artifact,
    upsert_ticker_payload,
)
from tests.helpers.constants import FIXTURE_API_KEY
from utils.handle_datetimes import get_epoch


@pytest.mark.asyncio
async def test_postgres_cold_path_serves_archived_date(client, postgres_pool):
    cold_date = "2023-01-03"
    ticker_payload = {
        "ticker": "AAPL",
        "date": get_epoch(cold_date),
        "macd": 1.23,
        "one_day_avg_mf": 12.3,
        "three_day_avg_mf": 11.1,
        "volume": 1000000,
        "three_day_avg_volume": 900000,
        "mfi": 55.0,
        "fcf": "12B",
        "frequencies": "T-1",
        "mentions_over_one_day": 0,
        "mentions_over_two_days": 0,
        "mentions_over_three_days": 0,
    }
    criterion_payload = {"one_day_avg_mf": [ticker_payload]}
    by_criteria_payload = {
        "by_one_day_avg_mf": [ticker_payload],
        "by_three_day_avg_mf": [ticker_payload],
        "by_volume": [ticker_payload],
        "by_three_day_avg_volume": [ticker_payload],
        "by_macd": [ticker_payload],
    }
    market_payload = {
        "SP500": 5000.0,
        "VIX": 12.0,
        "VIX1": 11.5,
        "VIX2": 11.0,
        "VIX_50days_EMA": 14.0,
        "normalazied_CVI_slope": 0.4,
    }

    await upsert_artifact(
        postgres_pool,
        cold_date,
        build_lists_artifact_key(None),
        by_criteria_payload,
        market="US",
    )
    await upsert_artifact(
        postgres_pool,
        cold_date,
        build_criterion_artifact_key("one_day_avg_mf", None),
        criterion_payload,
        market="US",
    )
    await upsert_artifact(
        postgres_pool,
        cold_date,
        MARKET_ARTIFACT_KEY,
        market_payload,
        market="US",
    )
    await upsert_ticker_payload(
        postgres_pool,
        cold_date,
        "AAPL",
        ticker_payload,
        market="US",
    )

    dates_response = await client.get(
        "/api/analytics/get_dates",
        params={"api_key": FIXTURE_API_KEY},
    )
    assert dates_response.status_code == 200
    date_strings = [item["date_string"] for item in dates_response.json()]
    assert cold_date in date_strings

    list_response = await client.get(
        "/api/analytics/get_analytics_lists_by_criterion",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": cold_date,
            "criterion": "one_day_avg_mf",
        },
    )
    assert list_response.status_code == 200
    assert list_response.json()["one_day_avg_mf"][0]["ticker"] == "AAPL"

    ticker_response = await client.get(
        "/api/analytics/get_ticker_analytics",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": cold_date,
            "ticker": "AAPL",
            "criterion": "one_day_avg_mf",
        },
    )
    assert ticker_response.status_code == 200
    assert ticker_response.json()["ticker"] == "AAPL"
    assert ticker_response.json()["fcf"] == "12B"

    market_response = await client.get(
        "/api/analytics/get_market_analytics",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": cold_date,
        },
    )
    assert market_response.status_code == 200
    assert market_response.json()["SP500"] == 5000.0


@pytest.mark.asyncio
async def test_postgres_cold_path_missing_payload_returns_404(client):
    response = await client.get(
        "/api/analytics/get_ticker_analytics",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": "2023-01-04",
            "ticker": "AAPL",
            "criterion": "one_day_avg_mf",
        },
    )
    assert response.status_code == 404
