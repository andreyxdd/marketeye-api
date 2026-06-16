"""E2e tests for liveness and readiness probes."""

import asyncio

import pytest

from core.build_info import APP_VERSION, get_deploy_revision
from db import mongodb
from db import postgres as postgres_module
from db import redis as redis_module


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
    assert data["redis"] == "ok"
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


@pytest.mark.asyncio
async def test_readyz_returns_503_when_redis_down(client):
    original_client = redis_module.db.client
    redis_module.db.client = None
    try:
        response = await client.get("/readyz")
    finally:
        redis_module.db.client = original_client

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["mongo"] == "ok"
    assert data["postgres"] == "ok"
    assert data["redis"] == "down"
    assert data["commit"] == get_deploy_revision()
    assert data["version"] == APP_VERSION


@pytest.mark.asyncio
async def test_readyz_returns_503_when_postgres_down(client, monkeypatch):
    async def _fail_connect():
        raise RuntimeError("PostgreSQL unavailable")

    original_pool = postgres_module.db.pool
    monkeypatch.setattr(postgres_module, "connect", _fail_connect)
    postgres_module.db.pool = None
    try:
        response = await client.get("/readyz")
    finally:
        postgres_module.db.pool = original_pool

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["mongo"] == "ok"
    assert data["postgres"] == "down"
    assert data["redis"] == "ok"
    assert data["commit"] == get_deploy_revision()
    assert data["version"] == APP_VERSION


@pytest.mark.asyncio
async def test_readyz_returns_503_when_probe_hangs(client, monkeypatch):
    from api.endpoints import health

    async def _hang():
        await asyncio.sleep(30)

    monkeypatch.setattr(health, "ping_postgres", _hang)

    response = await asyncio.wait_for(client.get("/readyz"), timeout=8.0)

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["postgres"] == "down"
