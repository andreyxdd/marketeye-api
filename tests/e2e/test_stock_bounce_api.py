"""Archive-first StockBounce API reads against PostgreSQL snapshots."""

from datetime import date, timedelta

import pytest

from db.crud.published_archive import (
    STOCK_BOUNCE_ARTIFACT_KEY,
    truncate_published_tables,
    upsert_artifact,
    upsert_published_date,
)
from services.stock_bounce.semantics import (
    build_snapshot,
    build_stock_bounce_analytics,
)
from tests.helpers.constants import FIXTURE_API_KEY


def _row(ticker="XYZ", close=147.0):
    start = date(2024, 1, 1)
    bars = []
    for index in range(19):
        open_price = 140.0
        bars.append(
            {
                "ticker": ticker,
                "date": (start + timedelta(days=index)).isoformat(),
                "open": open_price,
                "close": open_price * 0.99 if index < 18 else close,
                "high": 150.0,
                "low": 90.0,
                "volume": 1234567,
            }
        )
    return build_stock_bounce_analytics(bars)


@pytest.mark.asyncio
async def test_sessions_results_tracking_and_frequency_contract(client, postgres_pool):
    await truncate_published_tables(postgres_pool)
    await upsert_published_date(postgres_pool, "2024-01-19", market="US")
    snapshot = build_snapshot("2024-01-19", [_row()])
    await upsert_artifact(
        postgres_pool,
        "2024-01-19",
        STOCK_BOUNCE_ARTIFACT_KEY,
        snapshot,
        market="US",
    )
    await upsert_published_date(postgres_pool, "2024-01-18", market="US")
    await upsert_artifact(
        postgres_pool,
        "2024-01-18",
        STOCK_BOUNCE_ARTIFACT_KEY,
        {"schema_version": 1, "rows": [], "coverage": {"status": "exact"}},
        market="US",
    )

    sessions = await client.get(
        "/api/stock-bounce/v1/sessions", params={"api_key": FIXTURE_API_KEY}
    )
    assert sessions.status_code == 200
    assert sessions.json()["items"] == [
        {"epoch": 1705622400000.0, "date_string": "2024-01-19"}
    ]

    response = await client.get(
        "/api/stock-bounce/v1/results",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": "2024-01-19",
            "period": 6,
            "price_range": "100to299_99",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"][0]["ticker"] == "XYZ"
    assert payload["rows"][0]["open_close_change_pct"] == pytest.approx(5.0)
    assert payload["rows"][0]["frequencies"]
    assert payload["coverage"] == "exact"
    assert "bounce" not in payload["rows"][0]

    tracked = await client.get(
        "/api/stock-bounce/v1/results",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": "2024-01-19",
            "period": 6,
            "tickers": "MISSING,XYZ",
        },
    )
    assert tracked.status_code == 200
    assert [row["ticker"] for row in tracked.json()["rows"]] == ["XYZ"]
    assert tracked.json()["missing_tickers"] == ["MISSING"]


@pytest.mark.asyncio
async def test_missing_not_ready_and_no_match_responses(client, postgres_pool):
    await truncate_published_tables(postgres_pool)
    missing = await client.get(
        "/api/stock-bounce/v1/results",
        params={"api_key": FIXTURE_API_KEY, "date": "2024-01-19", "period": 1},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "SESSION_NOT_FOUND"

    await upsert_published_date(postgres_pool, "2024-01-19", market="US")
    not_ready = await client.get(
        "/api/stock-bounce/v1/results",
        params={"api_key": FIXTURE_API_KEY, "date": "2024-01-19", "period": 1},
    )
    assert not_ready.status_code == 409
    assert not_ready.json()["detail"]["code"] == "BOUNCE_SESSION_NOT_READY"

    await upsert_artifact(
        postgres_pool,
        "2024-01-19",
        STOCK_BOUNCE_ARTIFACT_KEY,
        build_snapshot("2024-01-19", [_row()]),
        market="US",
    )
    no_match = await client.get(
        "/api/stock-bounce/v1/results",
        params={
            "api_key": FIXTURE_API_KEY,
            "date": "2024-01-19",
            "period": 1,
            "price_range": "500to1000",
        },
    )
    assert no_match.status_code == 200
    assert no_match.json()["rows"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", [7, ["not", "a", "snapshot"]])
async def test_results_treats_non_object_snapshot_as_not_ready(
    client, postgres_pool, malformed
):
    await truncate_published_tables(postgres_pool)
    await upsert_published_date(postgres_pool, "2024-01-19", market="US")
    await upsert_artifact(
        postgres_pool,
        "2024-01-19",
        STOCK_BOUNCE_ARTIFACT_KEY,
        malformed,
        market="US",
    )

    response = await client.get(
        "/api/stock-bounce/v1/results",
        params={"api_key": FIXTURE_API_KEY, "date": "2024-01-19", "period": 1},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "BOUNCE_SESSION_NOT_READY"
