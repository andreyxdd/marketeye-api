import pytest

from tests.helpers.constants import FIXTURE_API_KEY, FIXTURE_DATE


@pytest.mark.asyncio
async def test_get_analytics_lists_by_criterion_to_market(client, monkeypatch):
    monkeypatch.setattr(
        "services.analytics_service.external_get_ticker_extra_analytics",
        lambda *args, **kwargs: {"mfi": 50.0},
    )
    monkeypatch.setattr(
        "services.analytics_service.get_quarterly_free_cash_flow_polygon",
        lambda *args, **kwargs: "",
    )

    response = await client.get(
        "/api/analytics/get_analytics_lists_by_criterion",
        params={
            "date": FIXTURE_DATE,
            "criterion": "one_day_avg_mf",
            "market": "TO",
            "api_key": FIXTURE_API_KEY,
        },
    )
    assert response.status_code == 200
    rows = response.json()["one_day_avg_mf"]
    assert rows
    assert rows[0]["ticker"] == "SHOP"
    assert rows[0]["fcf"] == ""
