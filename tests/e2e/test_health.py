"""E2e tests for liveness and readiness probes."""

import pytest

from core.build_info import APP_VERSION, get_deploy_revision
from db import mongodb


@pytest.mark.asyncio
async def test_healthz_returns_200_without_api_key(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data == {
        "status": "ok",
        "commit": get_deploy_revision(),
        "version": APP_VERSION,
    }


@pytest.mark.asyncio
async def test_readyz_returns_200_when_mongo_up(client):
    response = await client.get("/readyz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["mongo"] == "ok"
    assert data["postgres"] == "ok"
    assert data["commit"] == get_deploy_revision()
    assert data["version"] == APP_VERSION


@pytest.mark.asyncio
async def test_readyz_returns_503_when_mongo_down(client):
    original_client = mongodb.db.client
    mongodb.db.client = None
    try:
        response = await client.get("/readyz")
    finally:
        mongodb.db.client = original_client

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["mongo"] == "down"
    assert data["postgres"] == "ok"
    assert data["commit"] == get_deploy_revision()
    assert data["version"] == APP_VERSION
