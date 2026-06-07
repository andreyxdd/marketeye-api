import pytest

from tests.helpers.constants import FIXTURE_API_KEY, FIXTURE_DATE


@pytest.mark.asyncio
async def test_price_band_lte5_filters_by_close(client):
    response = await client.get(
        "/api/analytics/get_analytics_lists_by_criterion",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": FIXTURE_DATE,
            "criterion": "macd",
            "price_band": "lte5",
        },
    )
    assert response.status_code == 200
    rows = response.json()["macd"]
    assert len(rows) > 0
    for row in rows:
        assert "close" in row
        assert row["close"] <= 5.00


@pytest.mark.asyncio
async def test_price_band_boundary_five_dollars(client):
    response_lte5 = await client.get(
        "/api/analytics/get_analytics_lists_by_criterion",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": FIXTURE_DATE,
            "criterion": "macd",
            "price_band": "lte5",
        },
    )
    response_5to10 = await client.get(
        "/api/analytics/get_analytics_lists_by_criterion",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": FIXTURE_DATE,
            "criterion": "macd",
            "price_band": "5to10",
        },
    )
    lte5_tickers = {row["ticker"] for row in response_lte5.json()["macd"]}
    band_5to10_tickers = {row["ticker"] for row in response_5to10.json()["macd"]}

    assert "MSFT" in lte5_tickers
    assert "GOOG" in band_5to10_tickers
    assert "MSFT" not in band_5to10_tickers
    assert "GOOG" not in lte5_tickers


@pytest.mark.asyncio
async def test_invalid_price_band_returns_422(client):
    response = await client.get(
        "/api/analytics/get_analytics_lists_by_criterion",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": FIXTURE_DATE,
            "criterion": "macd",
            "price_band": "not_a_band",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_omit_price_band_unchanged(client):
    response = await client.get(
        "/api/analytics/get_analytics_lists_by_criterion",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": FIXTURE_DATE,
            "criterion": "macd",
        },
    )
    assert response.status_code == 200
    rows = response.json()["macd"]
    assert len(rows) == 20
    assert "close" not in rows[0]
