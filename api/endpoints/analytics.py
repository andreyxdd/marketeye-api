"""
Endpoints to access stock market analytics
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import Response

from utils.handle_validation import (
    validate_api_key,
    validate_date_string,
    validate_market,
)
from db.crud.tracking import CRITERIA
from db.mongodb import AsyncIOMotorClient, get_database
import services.analytics_service as analytics_service

analytics_router = APIRouter()


@analytics_router.get("/", tags=["Analytics"])
async def analytics():
    """Initial analytics route endpoint"""
    return Response("Hello World! It's an Analytics Router")


@analytics_router.get("/get_ticker_analytics", tags=["Analytics"])
async def read_ticker_analytics(
    date: str = Depends(validate_date_string),
    ticker: str = Query(
        default=None,
        description="Ticker representing the stock",
    ),
    criterion: str = Query(
        default=None,
        description="""
        Criterion by which the top 20 tickers are selected (used for frequency estimation).
        One of "one_day_avg_mf", "three_day_avg_mf", "volume", "three_day_avg_volume", "macd\"
        """,
    ),
    market: str = Depends(validate_market),
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    db: AsyncIOMotorClient = Depends(get_database),
):
    """Endpoint to get analytics (both base and extra) for a single stock"""
    return await analytics_service.get_ticker_analytics_response(
        db, date, ticker, market=market, criterion=criterion
    )


@analytics_router.get("/get_market_analytics", tags=["Analytics"])
async def read_market_analytics(
    date: str = Depends(validate_date_string),
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    db: AsyncIOMotorClient = Depends(get_database),
):
    """US market-wide analytics (SP500, VIX, CVI). No market= param."""
    return await analytics_service.get_market_analytics(db, date)


@analytics_router.get("/get_analytics_lists_by_criteria", tags=["Analytics"])
async def read_analytics_by_criteria(
    date: str = Depends(validate_date_string),
    market: str = Depends(validate_market),
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    db: AsyncIOMotorClient = Depends(get_database),
) -> dict:
    return await analytics_service.get_analytics_lists_by_criteria(db, date, market=market)


@analytics_router.get("/get_analytics_lists_by_criterion", tags=["Analytics"])
async def read_analytics_lists_by_criterion(
    date: str = Depends(validate_date_string),
    criterion: str = Query(
        default=None,
        description="""Criterion by which the top 20 tickers are selected.
        One of "one_day_avg_mf", "three_day_avg_mf", "volume", "three_day_avg_volume", "macd\"""",
    ),
    market: str = Depends(validate_market),
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    db: AsyncIOMotorClient = Depends(get_database),
) -> dict:
    if criterion not in CRITERIA:
        raise HTTPException(status_code=422, detail="No such criterion implemented.")

    rows = await analytics_service.get_analytics_sorted_by(
        db, date, criterion, market=market
    )
    return {criterion: rows}


@analytics_router.get("/get_dates", tags=["Analytics"])
async def read_dates(
    market: str = Depends(validate_market),
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    db: AsyncIOMotorClient = Depends(get_database),
) -> list:
    return await analytics_service.get_dates(db, market=market)


@analytics_router.get("/get_frequencies", tags=["Analytics"])
async def read_frequencies(
    date: str = Depends(validate_date_string),
    criterion: str = Query(
        default=None,
        description="""Criterion by which the top 20 tickers are selected.
        One of "one_day_avg_mf", "three_day_avg_mf", "volume", "three_day_avg_volume", "macd\"""",
    ),
    tickers: str = Query(
        default=None,
        description="""Stock tickers to count their frequency.
        Pass list as a string separating tickers by a comma without any spaces.""",
    ),
    market: str = Depends(validate_market),
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    db: AsyncIOMotorClient = Depends(get_database),
) -> dict:
    ticker_list = tickers.split(",")
    frequencies = await analytics_service.get_frequencies_for_tickers(
        db, date, criterion, ticker_list, market=market
    )
    return frequencies


@analytics_router.get("/get_free_cash_flow", tags=["Analytics"])
async def read_free_cash_flow(
    date: str = Depends(validate_date_string),
    ticker: str = Query(
        default=None,
        description="Ticker representing the stock",
    ),
    market: str = Depends(validate_market),
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
):
    return analytics_service.get_free_cash_flow(ticker, date, market=market)
