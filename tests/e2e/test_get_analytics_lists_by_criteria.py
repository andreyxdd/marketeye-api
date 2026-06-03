import pytest

from tests.helpers.constants import BY_CRITERIA_KEYS, FIXTURE_API_KEY, FIXTURE_DATE, LIST_LIMIT
from tests.helpers.contracts import assert_data_props_contract


@pytest.mark.asyncio
async def test_get_analytics_lists_by_criteria(client):
    response = await client.get(
        "/api/analytics/get_analytics_lists_by_criteria",
        params={"api_key": FIXTURE_API_KEY, "date": FIXTURE_DATE},
    )
    assert response.status_code == 200
    payload = response.json()
    for key in BY_CRITERIA_KEYS:
        assert key in payload
        rows = payload[key]
        assert len(rows) == LIST_LIMIT
        for row in rows:
            assert_data_props_contract(row)
