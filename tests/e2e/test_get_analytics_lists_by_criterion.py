import pytest

from tests.helpers.constants import (
    CRITERIA,
    FIXTURE_API_KEY,
    FIXTURE_DATE,
    FIXTURE_TICKERS,
    LIST_LIMIT,
)
from tests.helpers.contracts import assert_data_props_contract


@pytest.mark.asyncio
@pytest.mark.parametrize("criterion", CRITERIA)
async def test_get_analytics_lists_by_criterion(client, criterion):
    response = await client.get(
        "/api/analytics/get_analytics_lists_by_criterion",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": FIXTURE_DATE,
            "criterion": criterion,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert criterion in payload
    rows = payload[criterion]
    assert len(rows) == LIST_LIMIT
    assert rows[0]["ticker"] == FIXTURE_TICKERS[0]
    for row in rows:
        assert_data_props_contract(row)
    values = [row[criterion] for row in rows]
    assert values == sorted(values, reverse=True)


@pytest.mark.asyncio
async def test_invalid_criterion_returns_422(client):
    response = await client.get(
        "/api/analytics/get_analytics_lists_by_criterion",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": FIXTURE_DATE,
            "criterion": "not_a_criterion",
        },
    )
    assert response.status_code == 422
