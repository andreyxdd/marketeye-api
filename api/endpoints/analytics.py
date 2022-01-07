"""
Endpoints to access stock market analytics
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from core.settings import API_KEY
from utils.handle_external_apis import get_ticker_analytics

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
    if api_key != API_KEY:
        raise HTTPException(status_code=400, detail="Erreneous API key recieved.")

    return get_ticker_analytics(ticker, date)
