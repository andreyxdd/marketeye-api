import pytest

from tests.helpers.constants import (
    BY_CRITERIA_KEYS,
    CRITERIA,
    FIXTURE_API_KEY,
    FIXTURE_DATE,
    LIST_LIMIT,
)

ROUTES = [
    ("GET", "/api/analytics/get_dates", {"api_key": FIXTURE_API_KEY}),
    (
        "GET",
        "/api/analytics/get_market_analytics",
        {"api_key": FIXTURE_API_KEY, "date": FIXTURE_DATE},
    ),
    (
        "GET",
        "/api/analytics/get_ticker_analytics",
        {
            "api_key": FIXTURE_API_KEY,
            "date": FIXTURE_DATE,
            "ticker": "AAPL",
            "criterion": "one_day_avg_mf",
        },
    ),
    (
        "GET",
        "/api/analytics/get_analytics_lists_by_criterion",
        {
            "api_key": FIXTURE_API_KEY,
            "date": FIXTURE_DATE,
            "criterion": "one_day_avg_mf",
        },
    ),
    (
        "GET",
        "/api/analytics/get_analytics_lists_by_criteria",
        {"api_key": FIXTURE_API_KEY, "date": FIXTURE_DATE},
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,params", ROUTES)
async def test_missing_api_key_returns_403(client, method, path, params):
    params = {key: value for key, value in params.items() if key != "api_key"}
    response = await client.request(method, path, params=params)
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,params", ROUTES)
async def test_wrong_api_key_returns_403(client, method, path, params):
    params = dict(params)
    params["api_key"] = "wrong-key"
    response = await client.request(method, path, params=params)
    assert response.status_code == 403
