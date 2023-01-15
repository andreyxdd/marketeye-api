"""
Endpoints to access data processed with bounce algorithm
"""

from fastapi import APIRouter, Query, Depends
from fastapi.responses import Response

from db.crud.scrapes import get_mentions

from db.mongodb import AsyncIOMotorClient, get_database
from utils.handle_validation import validate_api_key, validate_date_string

scrapes_router = APIRouter()


@scrapes_router.get("/", tags=["Scrapes"])
async def scrapes():
    """
    Initial scrapes route endpoint
    """
    return Response("Hello World! It's a Scrapes Router")


@scrapes_router.get("/get_mentions", tags=["Scrapes"])
async def read_ticker_mentions(
    ticker: str = Query(
        default=None,
        description="Ticker representing the stock",
    ),
    date: str = Depends(validate_date_string),
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    db: AsyncIOMotorClient = Depends(get_database),
):
    """
    Endpoint to get mentions of a stock ticker on some popular media news websites

    Returns:
        dict: see get_mentions for the details
    """

    return {
        **await get_mentions(db, ticker, date),
    }
