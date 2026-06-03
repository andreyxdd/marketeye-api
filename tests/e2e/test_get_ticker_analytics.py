import pytest

from tests.helpers.constants import FIXTURE_API_KEY, FIXTURE_DATE
from tests.helpers.contracts import assert_data_props_contract


@pytest.mark.asyncio
async def test_get_ticker_analytics_aapl(client):
    response = await client.get(
        "/api/analytics/get_ticker_analytics",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": FIXTURE_DATE,
            "ticker": "AAPL",
            "criterion": "one_day_avg_mf",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "AAPL"
    assert_data_props_contract(payload)


@pytest.mark.asyncio
async def test_get_ticker_analytics_invalid_date(client):
    response = await client.get(
        "/api/analytics/get_ticker_analytics",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": "bad-date",
            "ticker": "AAPL",
            "criterion": "one_day_avg_mf",
        },
    )
    assert response.status_code == 422
