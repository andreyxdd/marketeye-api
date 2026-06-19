"""Hot-window dates prefer published Postgres list artifacts over live enrich."""

import pytest

from db.crud.published_archive import (
    build_criterion_artifact_key,
    build_lists_artifact_key,
    upsert_artifact,
)
from services import analytics_service
from services import read_router
from tests.helpers.constants import FIXTURE_API_KEY
from utils.handle_datetimes import get_epoch


@pytest.mark.asyncio
async def test_hot_date_serves_published_list_without_hot_enrich(
    client, postgres_pool, monkeypatch
):
    hot_date = "2024-06-03"
    ticker_payload = {
        "ticker": "PUB",
        "date": get_epoch(hot_date),
        "macd": 1.0,
        "one_day_avg_mf": 99.0,
        "three_day_avg_mf": 88.0,
        "volume": 1000,
        "three_day_avg_volume": 900,
        "mfi": 50.0,
        "fcf": "",
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

    await upsert_artifact(
        postgres_pool,
        hot_date,
        build_lists_artifact_key("10to20"),
        by_criteria_payload,
        market="US",
    )
    await upsert_artifact(
        postgres_pool,
        hot_date,
        build_criterion_artifact_key("one_day_avg_mf", "10to20"),
        criterion_payload,
        market="US",
    )

    async def hot_should_not_run(*_args, **_kwargs):
        raise AssertionError("hot enrich path should not run when published artifact exists")

    monkeypatch.setattr(read_router, "is_hot_date", lambda *args, **kwargs: True)
    monkeypatch.setattr(analytics_service, "get_analytics_sorted_by_hot", hot_should_not_run)
    monkeypatch.setattr(
        analytics_service, "get_analytics_lists_by_criteria_hot", hot_should_not_run
    )

    criterion_response = await client.get(
        "/api/analytics/get_analytics_lists_by_criterion",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": hot_date,
            "criterion": "one_day_avg_mf",
            "price_band": "10to20",
        },
    )
    assert criterion_response.status_code == 200
    assert criterion_response.json()["one_day_avg_mf"][0]["ticker"] == "PUB"

    criteria_response = await client.get(
        "/api/analytics/get_analytics_lists_by_criteria",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": hot_date,
            "price_band": "10to20",
        },
    )
    assert criteria_response.status_code == 200
    assert criteria_response.json()["by_one_day_avg_mf"][0]["ticker"] == "PUB"
