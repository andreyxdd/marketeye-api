"""FastAPI and bounded-read contract tests for StockBounce v2."""

from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

import api.endpoints.stock_bounce as endpoint
from main import app
from services.stock_bounce import reads
from services.stock_bounce.reads import StockBounceReadError
from tests.helpers.constants import FIXTURE_API_KEY


async def _pool_stub():
    return object()


@pytest.mark.asyncio
async def test_v2_requires_header_and_ignores_query_credentials(monkeypatch):
    async def sessions_stub(pool, cursor=None, limit=200):
        assert pool is not None
        return {"items": [], "next_cursor": None}

    monkeypatch.setattr(endpoint.stock_bounce_reads, "list_sessions_v2", sessions_stub)
    monkeypatch.setattr(endpoint, "get_pool", _pool_stub)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        missing = await client.get(
            "/api/stock-bounce/v2/sessions", params={"api_key": FIXTURE_API_KEY}
        )
        invalid = await client.get(
            "/api/stock-bounce/v2/sessions", headers={"X-API-Key": "wrong"}
        )
        valid = await client.get(
            "/api/stock-bounce/v2/sessions",
            headers={"X-API-Key": FIXTURE_API_KEY},
            params={"api_key": "wrong"},
        )

    assert missing.status_code == 401
    assert invalid.status_code == 403
    assert valid.status_code == 200
    for response in (missing, invalid):
        assert set(response.json()["detail"]) == {"code", "message", "details"}
        assert FIXTURE_API_KEY not in response.text


@pytest.mark.asyncio
async def test_v2_results_arguments_and_structured_errors(monkeypatch):
    async def result_stub(pool, *, date_string, lookback):
        assert date_string == "2024-01-02"
        assert lookback == 1260
        return {"schema_version": 2, "whole_market": {"rows": []}}

    monkeypatch.setattr(endpoint.stock_bounce_reads, "evaluate_session_v2", result_stub)
    monkeypatch.setattr(endpoint, "get_pool", _pool_stub)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/stock-bounce/v2/results",
            headers={"X-API-Key": FIXTURE_API_KEY},
            params={"date": "2024-01-02", "lookback": 1260},
        )
        invalid = await client.get(
            "/api/stock-bounce/v2/results",
            headers={"X-API-Key": FIXTURE_API_KEY},
            params={"date": "2024-01-02", "lookback": 1261},
        )

    assert response.status_code == 200
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "INVALID_QUERY"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code"),
    [(404, "SESSION_NOT_FOUND"), (409, "BOUNCE_SESSION_NOT_READY")],
)
async def test_v2_read_errors_keep_structure(monkeypatch, status, code):
    async def result_stub(pool, **kwargs):
        del pool, kwargs
        raise StockBounceReadError(status, code, "fixture failure")

    monkeypatch.setattr(endpoint.stock_bounce_reads, "evaluate_session_v2", result_stub)
    monkeypatch.setattr(endpoint, "get_pool", _pool_stub)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/stock-bounce/v2/results",
            headers={"X-API-Key": FIXTURE_API_KEY},
            params={"date": "2024-01-02", "lookback": 1},
        )
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code


class _ReadConnection:
    def __init__(self):
        self.snapshot_queries = 0
        self.bar_queries = 0

    async def fetchrow(self, query, *args):
        assert "stock_bounce:v2" not in query  # artifact key must be bound
        self.snapshot_queries += 1
        return {
            "known": True,
            "supported_lookback": 20,
            "payload": {
                "schema_version": 2,
                "market": "US",
                "date": "2024-03-05",
                "max_lookback": 20,
                "rows": [
                    {
                        "ticker": "ABC",
                        "open": 100.0,
                        "high": 111.0,
                        "close": 105.0,
                        "volume": 10,
                        "previous_all_time_high": 110.0,
                        "universes": ["whole_market"],
                    }
                ],
                "coverage": {
                    universe: {
                        "status": "exact",
                        "universe_provenance": "fixture",
                        "exclusions_count": 0,
                    }
                    for universe in ("whole_market", "macd_history")
                },
            },
        }

    async def fetch(self, query, *args):
        self.bar_queries += 1
        assert "ohlcv_bars" in query
        return [
            {
                "ticker": "ABC",
                "session_date": date(2024, 3, 4),
                "open": 100.0,
                "close": 95.0,
            }
        ]


class _ReadPool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        connection = self.connection

        class Acquisition:
            async def __aenter__(self):
                return connection

            async def __aexit__(self, *args):
                del args

        return Acquisition()


@pytest.mark.asyncio
async def test_result_read_uses_one_snapshot_and_one_set_based_bar_query():
    connection = _ReadConnection()

    result = await reads.evaluate_session_v2(
        _ReadPool(connection), date_string="2024-03-05", lookback=1
    )

    assert connection.snapshot_queries == 1
    assert connection.bar_queries == 1
    assert result["whole_market"]["rows"][0]["lookback_change_pct"] == -5.0


@pytest.mark.asyncio
async def test_v2_result_read_against_local_postgres(postgres_pool):
    """Exercise the two production SQL statements against the local archive."""
    from db.crud.published_archive import (
        STOCK_BOUNCE_V2_ARTIFACT_KEY,
        upsert_artifact,
    )
    from services.stock_bounce.semantics_v2 import build_snapshot_v2

    previous_day = "2030-01-02"
    target_day = "2030-01-03"
    coverage = {
        universe: {
            "status": "exact",
            "universe_provenance": "local_fixture",
            "exclusions_count": 0,
        }
        for universe in ("whole_market", "macd_history")
    }
    previous_snapshot = build_snapshot_v2(
        previous_day, [], coverage=coverage, max_lookback=0
    )
    target_snapshot = build_snapshot_v2(
        target_day,
        [
            {
                "ticker": "ABC",
                "open": 100.0,
                "high": 111.0,
                "close": 105.0,
                "volume": 1000,
                "previous_all_time_high": 110.0,
                "universes": ["whole_market"],
            }
        ],
        coverage=coverage,
        max_lookback=1,
    )
    await upsert_artifact(
        postgres_pool, previous_day, STOCK_BOUNCE_V2_ARTIFACT_KEY, previous_snapshot
    )
    await upsert_artifact(
        postgres_pool, target_day, STOCK_BOUNCE_V2_ARTIFACT_KEY, target_snapshot
    )
    async with postgres_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO ohlcv_bars(
                market, ticker, session_date, open, high, low, close, volume
            ) VALUES('US', 'ABC', $1, 100, 100, 90, 95, 1000)
            ON CONFLICT(market, ticker, session_date) DO UPDATE SET
                open = EXCLUDED.open, high = EXCLUDED.high,
                low = EXCLUDED.low, close = EXCLUDED.close, volume = EXCLUDED.volume
            """,
            date(2030, 1, 2),
        )
    try:
        result = await reads.evaluate_session_v2(
            postgres_pool, date_string=target_day, lookback=1
        )
        assert result["whole_market"]["rows"][0]["lookback_change_pct"] == -5.0
    finally:
        async with postgres_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM published_dates WHERE session_date = ANY($1::date[])",
                [date(2030, 1, 2), date(2030, 1, 3)],
            )
            await conn.execute(
                "DELETE FROM ohlcv_bars WHERE market = 'US' AND ticker = 'ABC' AND session_date = $1",
                date(2030, 1, 2),
            )
