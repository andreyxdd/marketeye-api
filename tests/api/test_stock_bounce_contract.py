"""FastAPI validation and structured error mapping for StockBounce v1."""

import pytest
from httpx import ASGITransport, AsyncClient

import api.endpoints.stock_bounce as endpoint
from main import app
from services.stock_bounce.reads import StockBounceReadError
from tests.helpers.constants import FIXTURE_API_KEY


@pytest.mark.asyncio
async def test_sessions_contract_and_pagination_arguments(monkeypatch):
    async def sessions_stub(pool, cursor=None, limit=200):
        assert pool is not None
        assert cursor == "opaque"
        assert limit == 500
        return {"items": [], "next_cursor": None}

    monkeypatch.setattr(endpoint.stock_bounce_reads, "list_sessions", sessions_stub)
    monkeypatch.setattr(endpoint, "get_pool", _pool_stub)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/stock-bounce/v1/sessions",
            params={"api_key": FIXTURE_API_KEY, "cursor": "opaque", "limit": 500},
        )
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


async def _pool_stub():
    return object()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"date": "2024-13-01", "period": 1},
        {"date": "2024-01-01", "period": 19},
        {"date": "2024-01-01", "period": 1, "price_range": "under48"},
        {"date": "2024-01-01", "period": 1, "tickers": "AAPL,AAPL"},
        {"date": "2024-01-01", "period": 1, "tickers": ""},
    ],
)
async def test_invalid_results_queries_return_422(params):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/stock-bounce/v1/results",
            params={"api_key": FIXTURE_API_KEY, **params},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_not_ready_and_storage_errors_have_structured_details(monkeypatch):
    async def not_ready(pool, **kwargs):
        del pool, kwargs
        raise StockBounceReadError(
            409,
            "BOUNCE_SESSION_NOT_READY",
            "StockBounce publication is incomplete for US 2024-01-01",
        )

    monkeypatch.setattr(endpoint.stock_bounce_reads, "evaluate_session", not_ready)
    monkeypatch.setattr(endpoint, "get_pool", _pool_stub)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/stock-bounce/v1/results",
            params={"api_key": FIXTURE_API_KEY, "date": "2024-01-01", "period": 1},
        )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "BOUNCE_SESSION_NOT_READY"


@pytest.mark.asyncio
async def test_pool_connection_failure_maps_to_503(monkeypatch):
    async def unavailable():
        raise RuntimeError("database offline")

    monkeypatch.setattr(endpoint, "get_pool", unavailable)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/stock-bounce/v1/sessions",
            params={"api_key": FIXTURE_API_KEY},
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "BOUNCE_READ_MODEL_UNAVAILABLE"
