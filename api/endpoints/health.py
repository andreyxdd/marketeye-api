"""Liveness and readiness probe endpoints."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from typing import Optional

from core.build_info import APP_VERSION, get_deploy_revision
from db.mongodb import get_database
from db.postgres import ping as ping_postgres
from db.redis import ping as ping_redis

health_router = APIRouter()


def _probe_payload(
    mongo: Optional[str] = None, postgres: Optional[str] = None, redis: Optional[str] = None
) -> dict:
    payload = {
        "status": "ok",
        "commit": get_deploy_revision(),
        "version": APP_VERSION,
    }
    if mongo is not None:
        payload["mongo"] = mongo
    if postgres is not None:
        payload["postgres"] = postgres
    if redis is not None:
        payload["redis"] = redis
    return payload


@health_router.get("/healthz", tags=["Health"])
async def healthz():
    """Liveness probe — always returns HTTP 200 when the process is up."""
    return _probe_payload()


@health_router.get("/readyz", tags=["Health"])
async def readyz():
    """Readiness probe — returns HTTP 503 when MongoDB, PostgreSQL, or Redis is unreachable."""
    payload = _probe_payload(mongo="ok", postgres="ok", redis="ok")
    has_failure = False

    try:
        db = await get_database()
        if db is None:
            raise RuntimeError("MongoDB client not initialized")
        await db.admin.command("ping")
    except Exception:  # pylint: disable=broad-except
        has_failure = True
        payload["mongo"] = "down"

    try:
        await ping_postgres()
    except Exception:  # pylint: disable=broad-except
        has_failure = True
        payload["postgres"] = "down"

    try:
        await ping_redis()
    except Exception:  # pylint: disable=broad-except
        has_failure = True
        payload["redis"] = "down"

    if has_failure:
        payload["status"] = "unavailable"
        return JSONResponse(status_code=503, content=payload)
    return payload
