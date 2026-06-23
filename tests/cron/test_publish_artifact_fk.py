"""Regression: upsert_artifact must ensure published_dates parent row."""

from datetime import date

import pytest

from db.crud.published_archive import truncate_published_tables, upsert_artifact


@pytest.fixture(autouse=True)
async def _clean_published_tables(postgres_pool):
    await truncate_published_tables(postgres_pool)
    yield
    await truncate_published_tables(postgres_pool)


@pytest.mark.asyncio
async def test_upsert_artifact_creates_published_date_parent(postgres_pool):
    date_string = "2024-06-03"
    market = "US"
    artifact_key = "lists_by_criteria:all"
    payload = {"lists": []}

    await upsert_artifact(
        postgres_pool,
        date_string,
        artifact_key,
        payload,
        market=market,
    )

    async with postgres_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT session_date, market
            FROM published_dates
            WHERE session_date = $1 AND market = $2
            """,
            date.fromisoformat(date_string),
            market,
        )

    assert row is not None
    assert row["session_date"].isoformat() == date_string
    assert row["market"] == market
