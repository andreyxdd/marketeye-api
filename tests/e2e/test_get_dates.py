import pytest

from db.crud.published_archive import truncate_published_tables
from tests.helpers.constants import FIXTURE_API_KEY, FIXTURE_DATE, HISTORY_WEEKDAYS


@pytest.mark.asyncio
async def test_get_dates_shape_and_anchor(client, postgres_pool):
    # Session PG may hold archived cold dates from other tests; dates union includes them.
    await truncate_published_tables(postgres_pool)
    response = await client.get(
        "/api/analytics/get_dates", params={"api_key": FIXTURE_API_KEY}
    )
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == HISTORY_WEEKDAYS
    for item in payload:
        assert "epoch" in item
        assert "date_string" in item
    date_strings = [item["date_string"] for item in payload]
    assert FIXTURE_DATE in date_strings
