"""CVI slope tests for paired adv/dec aggregation."""

import pytest

from core.settings import MONGO_DB_NAME
from db.crud.analytics import get_normalazied_cvi_slope
from tests.helpers.constants import FIXTURE_DATE
from utils.handle_datetimes import get_epoch, get_past_date


@pytest.mark.asyncio
async def test_cvi_slope_matches_fixture_data(mongo_client):
    slope = await get_normalazied_cvi_slope(mongo_client, FIXTURE_DATE)
    assert isinstance(slope, float)
    assert slope != 0.0


@pytest.mark.asyncio
async def test_cvi_slope_handles_adv_only_day(mongo_client):
    skew_date = get_past_date(1, FIXTURE_DATE)
    epoch = get_epoch(skew_date)
    await mongo_client[MONGO_DB_NAME]["analytics"].delete_many({"date": epoch, "market": "US"})
    await mongo_client[MONGO_DB_NAME]["analytics"].insert_many(
        [
            {
                "market": "US",
                "ticker": "ONLYUP",
                "date": epoch,
                "one_day_open_close_change": 0.02,
            }
        ]
    )

    slope = await get_normalazied_cvi_slope(mongo_client, FIXTURE_DATE)
    assert isinstance(slope, float)
