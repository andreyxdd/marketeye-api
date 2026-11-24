"""Liveness, readiness, and production freshness probe endpoints."""

import asyncio
import logging
from time import monotonic

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from typing import Optional

from core.build_info import APP_VERSION, get_deploy_revision
from db.mongodb import get_database
from db.postgres import get_pool as get_postgres_pool
from db.postgres import ping as ping_postgres
from db.redis import ping as ping_redis
from services.cron_dates import freshness_report

health_router = APIRouter()
logger = logging.getLogger(__name__)

_PROBE_TIMEOUT_SECONDS = 5.0
_FRESHNESS_CACHE_SECONDS = 60.0
_freshness_cache = None
_freshness_cache_lock = asyncio.Lock()


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
        async def _ping_mongo():
            db = await get_database()
            if db is None:
                raise RuntimeError("MongoDB client not initialized")
            await db.admin.command("ping")

        await asyncio.wait_for(_ping_mongo(), timeout=_PROBE_TIMEOUT_SECONDS)
    except Exception:  # pylint: disable=broad-except
        has_failure = True
        payload["mongo"] = "down"

    try:
        await asyncio.wait_for(ping_postgres(), timeout=_PROBE_TIMEOUT_SECONDS)
    except Exception:  # pylint: disable=broad-except
        has_failure = True
        payload["postgres"] = "down"

    try:
        await asyncio.wait_for(ping_redis(), timeout=_PROBE_TIMEOUT_SECONDS)
    except Exception:  # pylint: disable=broad-except
        has_failure = True
        payload["redis"] = "down"

    if has_failure:
        payload["status"] = "unavailable"
        return JSONResponse(status_code=503, content=payload)
    return payload


def _unavailable_freshness_report() -> dict:
    from datetime import datetime, timezone

    us_components = {
        name: {"status": "unavailable", "latest_session": None}
        for name in ("analytics", "stock_bounce_v1", "stock_bounce_v2")
    }
    return {
        "status": "unavailable",
        "checked_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "markets": {
            "US": {"expected_session": None, "components": us_components},
            "TO": {
                "expected_session": None,
                "components": {
                    "analytics": {"status": "unavailable", "latest_session": None}
                },
            },
        },
    }


async def _cached_freshness_report():
    global _freshness_cache
    now = monotonic()
    if (
        _freshness_cache is not None
        and now - _freshness_cache[0] < _FRESHNESS_CACHE_SECONDS
    ):
        return _freshness_cache[1]
    async with _freshness_cache_lock:
        now = monotonic()
        if (
            _freshness_cache is not None
            and now - _freshness_cache[0] < _FRESHNESS_CACHE_SECONDS
        ):
            return _freshness_cache[1]
        try:
            pool = await get_postgres_pool()
            report = await freshness_report(pool)
        except Exception as error:  # pylint: disable=broad-except
            logger.error(
                "Freshness report generation failed (%s)", type(error).__name__
            )
            report = _unavailable_freshness_report()
        _freshness_cache = (monotonic(), report)
        return report


@health_router.get("/freshness", tags=["Health"])
async def freshness():
    """Return production archive freshness without exposing application data."""
    report = await _cached_freshness_report()
    headers = {"Cache-Control": "no-store"}
    status_code = 200
    if report["status"] != "fresh":
        status_code = 503
        headers["Retry-After"] = "300"
    return JSONResponse(status_code=status_code, content=report, headers=headers)
