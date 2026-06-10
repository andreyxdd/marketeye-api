"""Liveness and readiness probe endpoints."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.build_info import APP_VERSION, get_deploy_revision
from db.mongodb import get_database

health_router = APIRouter()


def _probe_payload(mongo: str | None = None) -> dict:
    payload = {
        "status": "ok",
        "commit": get_deploy_revision(),
        "version": APP_VERSION,
    }
    if mongo is not None:
        payload["mongo"] = mongo
    return payload


@health_router.get("/healthz", tags=["Health"])
async def healthz():
    """Liveness probe — always returns HTTP 200 when the process is up."""
    return _probe_payload()


@health_router.get("/readyz", tags=["Health"])
async def readyz():
    """Readiness probe — returns HTTP 503 when MongoDB is unreachable."""
    payload = _probe_payload(mongo="ok")
    try:
        db = await get_database()
        if db is None:
            raise RuntimeError("MongoDB client not initialized")
        await db.admin.command("ping")
        return payload
    except Exception:  # pylint: disable=broad-except
        payload["status"] = "unavailable"
        payload["mongo"] = "down"
        return JSONResponse(status_code=503, content=payload)
