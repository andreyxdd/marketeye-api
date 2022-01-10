"""
Endpoints to access stock market analytics
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response

from core.settings import API_KEY
from utils.handle_datetimes import is_valid_date
from utils.handle_external_apis import (
    get_ticker_analytics,
    get_market_sp500,
    get_market_vixs,
)
from db.crud.analytics import (
    get_normalazied_cvi_slope,
    get_analytics_sorted_by_one_day_avg_mf,
    get_analytics_sorted_by_three_day_avg_mf,
    get_analytics_by_five_precents_open_close_change,
    get_analytics_sorted_by_volume,
    get_analytics_sorted_by_three_day_avg_volume,
    get_dates,
)
from db.mongodb import AsyncIOMotorClient, get_database

analytics_router = APIRouter()


@analytics_router.get("/")
async def home():
    """
    Initial analytics route

    Returns:

        Response: welcome sign
    """
    return Response("Hello World! It's a Analytics Router")


@analytics_router.get("/get_ticker_analytics")
async def read_ticker_analytics(date: str, ticker: str, api_key: str):
    """
    Endpoint to get analytics (both base and extra) for a single stock

    Args:
        date (str): analytics for which date
        ticker (str): ticker representing the stock
        api_key (str): key to allow/disallow a request

    Raises:
        HTTPException: Incorrect API key provided

    Returns:
        dict: see compute_base_analytics and compute_extra_analytics for details
    """
    is_valid_date(date)

    if api_key != API_KEY:
        raise HTTPException(status_code=400, detail="Erreneous API key recieved.")

    return get_ticker_analytics(
        ticker,
        date,
        600,
        365,
    )


@analytics_router.get("/get_market_analytics")
async def read_market_analytics(
    date: str, api_key: str, db: AsyncIOMotorClient = Depends(get_database)
):
    """
    Endpoint to get analytics for market as a whole

    Args:
        date (str): analytics for which date
        api_key (str): key to allow/disallow a request

    Raises:
        HTTPException: Incorrect API key provided

    Returns:
        dict:
    """
    is_valid_date(date)

    if api_key != API_KEY:
        raise HTTPException(status_code=400, detail="Erreneous API key recieved.")

    return {
        "SP500": get_market_sp500(date),
        **get_market_vixs(date),
        "normalazied_CVI_slope": await get_normalazied_cvi_slope(db, date),
    }


@analytics_router.get("/get_analytics_lists_by_criteria")
async def read_analytics_by_criteria(
    date: str, api_key: str, db: AsyncIOMotorClient = Depends(get_database)
) -> dict:
    """
    Endpoint to get analytics (both base and extra) for a single stock

    Args:
        date (str): analytics for which date
        ticker (str): ticker representing the stock
        api_key (str): key to allow/disallow a request

    Raises:
        HTTPException: Incorrect API key provided

    Returns:
        dict:
            each field is a list of outputs for the following
            functions compute_base_analytics and compute_extra_analytics for details
    """
    is_valid_date(date)

    if api_key != API_KEY:
        raise HTTPException(status_code=400, detail="Erreneous API key recieved.")

    return {
        "by_one_day_avg_mf": await get_analytics_sorted_by_one_day_avg_mf(db, date),
        "by_three_day_avg_mf": await get_analytics_sorted_by_three_day_avg_mf(db, date),
        "by_five_prec_open_close_change": await get_analytics_by_five_precents_open_close_change(
            db, date
        ),
        "by_volume": await get_analytics_sorted_by_volume(db, date),
        "by_three_day_avg_volume": await get_analytics_sorted_by_three_day_avg_volume(
            db, date
        ),
    }


@analytics_router.get("/get_dates")
async def read_dates(
    api_key: str, db: AsyncIOMotorClient = Depends(get_database)
) -> dict:
    """
    Endpoint to get all the distinctive dates present in the analytics collection

    Args:
        api_key (str): key to allow/disallow a request

    Raises:
        HTTPException: Incorrect API key provided

    Returns:
        dict: one field ("dates") correspongding to list of epoch dates
    """
    if api_key != API_KEY:
        raise HTTPException(status_code=400, detail="Erreneous API key recieved.")

    return {"dates": await get_dates(db)}
