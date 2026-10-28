"""Thin FastAPI adapter for archive-first StockBounce API v1."""

from datetime import datetime
import re

from fastapi import APIRouter, Depends, HTTPException, Query

from db.postgres import get_pool
from services.stock_bounce import reads as stock_bounce_reads
from services.stock_bounce.reads import StockBounceReadError
from services.stock_bounce.semantics import PRICE_RANGES
from utils.handle_validation import validate_api_key


stock_bounce_router = APIRouter()
_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,19}$")


def _error(status_code: int, code: str, message: str, details=None):
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "details": details or {}},
    )


def _date(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
        if parsed.isoformat() != value:
            raise ValueError("non-canonical date")
        return value
    except ValueError as error:
        raise _error(422, "INVALID_DATE", "date must use YYYY-MM-DD") from error


def _tickers(value):
    if value is None:
        return None
    values = value.split(",")
    if not 1 <= len(values) <= 20 or any(not item for item in values):
        raise _error(422, "INVALID_TICKERS", "tickers must contain 1-20 unique symbols")
    normalized = [item.upper() for item in values]
    if len(set(normalized)) != len(normalized) or any(
        not _TICKER.fullmatch(item) for item in normalized
    ):
        raise _error(422, "INVALID_TICKERS", "tickers must contain 1-20 unique symbols")
    return normalized


async def _call(function, *args, **kwargs):
    try:
        return await function(*args, **kwargs)
    except StockBounceReadError as error:
        raise _error(
            error.status_code, error.code, error.message, error.details
        ) from error
    except Exception as error:
        raise _error(
            503,
            "BOUNCE_READ_MODEL_UNAVAILABLE",
            "StockBounce archive storage is unavailable",
        ) from error


@stock_bounce_router.get("/sessions", tags=["StockBounce"])
async def read_sessions(
    cursor: str = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    api_key: str = Depends(validate_api_key),  # pylint: disable=unused-argument
):
    pool = await _call(get_pool)
    return await _call(
        stock_bounce_reads.list_sessions, pool, cursor=cursor, limit=limit
    )


@stock_bounce_router.get("/results", tags=["StockBounce"])
async def read_results(
    date: str = Query(...),
    period: int = Query(..., ge=1, le=18),
    price_range: str = Query(default="all"),
    tickers: str = Query(default=None),
    api_key: str = Depends(validate_api_key),  # pylint: disable=unused-argument
):
    date_string = _date(date)
    if price_range not in PRICE_RANGES:
        raise _error(422, "INVALID_PRICE_RANGE", "Unsupported StockBounce price range")
    ticker_list = _tickers(tickers)
    pool = await _call(get_pool)
    return await _call(
        stock_bounce_reads.evaluate_session,
        pool,
        date_string=date_string,
        period=period,
        price_range=price_range,
        tickers=ticker_list,
    )
