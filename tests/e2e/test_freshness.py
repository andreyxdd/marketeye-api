"""E2e tests for the public production freshness report."""

import pytest

from api.endpoints import health


FRESH_REPORT = {
    "status": "fresh",
    "checked_at": "2026-11-24T06:16:28Z",
    "markets": {
        "US": {
            "expected_session": "2026-11-23",
            "components": {
                "analytics": {"status": "fresh", "latest_session": "2026-11-23"},
                "stock_bounce_v1": {
                    "status": "fresh",
                    "latest_session": "2026-11-23",
                },
                "stock_bounce_v2": {
                    "status": "fresh",
                    "latest_session": "2026-11-23",
                },
            },
        },
        "TO": {
            "expected_session": "2026-11-23",
            "components": {
                "analytics": {"status": "fresh", "latest_session": "2026-11-23"}
            },
        },
    },
}


@pytest.mark.asyncio
async def test_freshness_returns_fresh_report_without_api_key(client, monkeypatch):
    async def report_stub(pool):
        del pool
        return FRESH_REPORT

    monkeypatch.setattr(health, "freshness_report", report_stub)

    response = await client.get("/freshness")

    assert response.status_code == 200
    assert response.json() == FRESH_REPORT
    assert response.headers["Cache-Control"] == "no-store"
    assert "Retry-After" not in response.headers


@pytest.mark.asyncio
async def test_freshness_returns_503_with_retry_headers_for_stale_report(
    client, monkeypatch
):
    stale_report = {
        "status": "stale",
        "checked_at": "2026-11-24T06:16:28Z",
        "markets": {
            "US": {
                "expected_session": "2026-11-23",
                "components": {
                    "analytics": {"status": "stale", "latest_session": "2026-11-20"},
                    "stock_bounce_v1": {
                        "status": "stale",
                        "latest_session": "2026-11-20",
                    },
                    "stock_bounce_v2": {
                        "status": "stale",
                        "latest_session": "2026-11-20",
                    },
                },
            },
            "TO": {
                "expected_session": "2026-11-23",
                "components": {
                    "analytics": {"status": "fresh", "latest_session": "2026-11-23"}
                },
            },
        },
    }

    async def report_stub(pool):
        del pool
        return stale_report

    monkeypatch.setattr(health, "freshness_report", report_stub)

    response = await client.get("/freshness")

    assert response.status_code == 503
    assert response.json() == stale_report
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Retry-After"] == "300"


@pytest.mark.asyncio
async def test_freshness_reuses_report_for_sixty_seconds(client, monkeypatch):
    calls = []

    async def report_stub(pool):
        del pool
        calls.append("report")
        return FRESH_REPORT

    monkeypatch.setattr(health, "freshness_report", report_stub)

    first = await client.get("/freshness")
    second = await client.get("/freshness")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert calls == ["report"]


@pytest.fixture(autouse=True)
def _clear_freshness_report_cache():
    health._freshness_cache = None
    yield
    health._freshness_cache = None


@pytest.mark.asyncio
async def test_freshness_returns_sanitized_unavailable_report_on_internal_failure(
    client, monkeypatch, caplog
):
    import logging

    async def report_failure(pool):
        del pool
        raise RuntimeError("private stack and credential-bearing-url")

    caplog.set_level(logging.ERROR, logger="api.endpoints.health")
    monkeypatch.setattr(health, "freshness_report", report_failure)

    response = await client.get("/freshness")

    assert response.status_code == 503
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Retry-After"] == "300"
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["markets"]["US"]["components"]["analytics"]["status"] == "unavailable"
    assert data["markets"]["TO"]["components"]["analytics"]["status"] == "unavailable"
    assert "private stack" not in response.text
    assert "credential-bearing-url" not in response.text
    assert "credential-bearing-url" not in caplog.text
    assert "RuntimeError" in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.fixture
def mongo_client():
    """The route tests stub the report and need no ticker/database fixtures."""
    return None


@pytest.fixture(autouse=True)
def _freshness_pool(monkeypatch):
    async def pool_stub():
        return object()

    monkeypatch.setattr(health, "get_postgres_pool", pool_stub)


@pytest.mark.asyncio
async def test_freshness_refreshes_report_after_sixty_seconds(client, monkeypatch):
    calls = []

    async def report_stub(pool):
        del pool
        calls.append("report")
        return FRESH_REPORT

    monkeypatch.setattr(health, "freshness_report", report_stub)
    monkeypatch.setattr(
        health,
        "monotonic",
        iter([100.0, 100.0, 100.0, 160.0, 160.0, 160.0]).__next__,
    )

    await client.get("/freshness")
    await client.get("/freshness")

    assert calls == ["report", "report"]
