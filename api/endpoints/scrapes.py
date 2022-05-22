"""
Endpoints to access stock ticker scrapes data
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response

from core.settings import API_KEY
from utils.handle_datetimes import is_valid_date
from db.crud.scrapes import get_mentions

from db.mongodb import AsyncIOMotorClient, get_database

scrapes_router = APIRouter()


@scrapes_router.get("/")
async def home():
    """
    Initial analytics route

    Returns:

        Response: welcome sign
    """
    return Response("Hello World! It's a Scrapes Router")


@scrapes_router.get("/get_mentions")
async def read_ticker_mentions(
    date: str,
    stockticker: str,
    apikey: str,
    database: AsyncIOMotorClient = Depends(get_database),
):
    """
    Endpoint to get mentions of a stock ticker
    on the popular media news websites

    Args:
        date (str): date in the format of YYYY-MM-DD
        stockticker (str): the ticker representing the stock
        apikey (str): key for the request

    Raises:
        HTTPException: An incorrect API key provided

    Returns:
        dict: see get_mentions for the details
    """
    is_valid_date(date)

    if apikey != API_KEY:
        raise HTTPException(status_code=400, detail="Erreneous API key recieved.")

    return {
        **await get_mentions(database, stockticker, date),
    }
