import pytest

from db.crud.analytics import get_normalazied_cvi_slope
from tests.helpers.constants import FIXTURE_API_KEY, FIXTURE_DATE
from tests.helpers.contracts import assert_market_contract


@pytest.mark.asyncio
async def test_get_market_analytics_success(client):
    response = await client.get(
        "/api/analytics/get_market_analytics",
        params={"api_key": FIXTURE_API_KEY, "date": FIXTURE_DATE},
    )
    assert response.status_code == 200
    assert_market_contract(response.json())


@pytest.mark.asyncio
async def test_get_market_analytics_uses_real_cvi(mongo_client, client):
    expected = await get_normalazied_cvi_slope(mongo_client, FIXTURE_DATE)
    response = await client.get(
        "/api/analytics/get_market_analytics",
        params={"api_key": FIXTURE_API_KEY, "date": FIXTURE_DATE},
    )
    assert response.status_code == 200
    assert response.json()["normalazied_CVI_slope"] == pytest.approx(expected)
    assert response.json()["normalazied_CVI_slope"] != 0.65


@pytest.mark.asyncio
async def test_get_market_analytics_invalid_date(client):
    response = await client.get(
        "/api/analytics/get_market_analytics",
        params={"api_key": FIXTURE_API_KEY, "date": "not-a-date"},
    )
    assert response.status_code == 422
