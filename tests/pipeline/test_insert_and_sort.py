import pytest

from db.crud.analytics import compute_base_analytics_and_insert, get_analytics_sorted_by
from tests.helpers.constants import FIXTURE_DATE, PIPELINE_TICKERS


@pytest.mark.asyncio
async def test_insert_and_sort(pipeline_db):
    await compute_base_analytics_and_insert(pipeline_db, FIXTURE_DATE)
    rows = await get_analytics_sorted_by(
        pipeline_db, FIXTURE_DATE, "one_day_avg_mf", len(PIPELINE_TICKERS)
    )
    assert len(rows) == len(PIPELINE_TICKERS)
    assert {row["ticker"] for row in rows} == set(PIPELINE_TICKERS)
    mf_values = [row["one_day_avg_mf"] for row in rows]
    assert mf_values == sorted(mf_values, reverse=True)
