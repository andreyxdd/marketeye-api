"""
Methods to retrieve data from the timesereis collection
"""
import asyncio
from time import sleep
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.settings import MONGO_DB_NAME, QUANDL_RATE_LIMIT, QUANDL_SLEEP_MINUTES
from db.crud.tracking import get_analytics_frequencies
from db.mongodb import AsyncIOMotorClient
from db.crud.scrapes import get_mentions
from db.redis import use_cache_async
from utils.handle_datetimes import get_date_string, get_epoch, get_last_quater_date
from utils.handle_calculations import get_slope_normalized
from utils.handle_external_apis import (
    get_quandl_tickers,
    get_quaterly_free_cash_flow,
    get_ticker_base_analytics,
    get_ticker_extra_analytics,
)

MONGO_COLLECTION_NAME = "timeseries"


async def get_timeseries_tickers(conn: AsyncIOMotorClient, date: str) -> "list[str]":
    """
    Function that returns a list of all the tickers that
    are present in the analytics mongodb collection for the given date

    Args:
        conn (AsyncIOMotorClient): db-connection string
        date (str): date to search for

    Returns:
        list[str]: list of strings (tickers' names)
    """
    epoch_date = get_epoch(date)
    cursor = await conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].distinct(
        "ticker", {"date": epoch_date}
    )
    return list(cursor)

# TODO: criterion can be only of a certain type


async def get_top_tickers_by_criterion(
    conn: AsyncIOMotorClient, date: str, criterion: str, limit: Optional[int] = 20
) -> str:
    """
    Function to get top 20 stocks by the given criterion

    Args:
        conn (AsyncIOMotorClient): db-connection string
        date (str): date to serach for
        criterion (str): criterion by which to sort analytics
        lim (Optional[int], optional): number of stocks to return. Defaults to 20.

    Returns:
        list[dict]:
            list of dict. See compute_base_analytics and compute_extra_analytics for details
    """

    epoch_date = get_epoch(date)
    cursor = (
        conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME]
        .find(
            {"date": epoch_date},
            {"_id": False, "ticker": True},
        )
        .sort(criterion, -1)
        .limit(limit)
    )
    items = await cursor.to_list(length=limit)

    return [item["ticker"] for item in items]
