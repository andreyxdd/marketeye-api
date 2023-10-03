"""

"""
import logging

from core.settings import MONGO_DB_NAME, QUANDL_RATE_LIMIT, QUANDL_SLEEP_MINUTES
from db.crud.tracking import get_analytics_frequencies
from db.insert.timeseries import update_single_ticker
from db.mongodb import AsyncIOMotorClient
from db.crud.scrapes import get_mentions
from db.redis import use_cache_async
from db.retrieve.timeseries import get_timeseries_tickers, get_top_tickers_by_criterion
from utils.handle_datetimes import get_date_string, get_epoch, get_last_quater_date, get_past_date
from utils.handle_calculations import get_slope_normalized
from utils.quandl import get_single_ticker_analytics, get_quandl_tickers

MONGO_COLLECTION_NAME = "macd"

log = logging.getLogger(__name__)


async def insert_top_by_macd(conn: AsyncIOMotorClient, date: str):
    """_summary_

    Args:
        conn (AsyncIOMotorClient): _description_
        date (str): _description_
    """
    tickers = await get_top_tickers_by_criterion(conn, date, "macd", 5)

    epoch_date = get_epoch(date)

    if tickers:
        await conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].find_one_and_replace(
            {"date": epoch_date},
            {"date": epoch_date, "tickers": ",".join(tickers)},
            upsert=True
        )


async def count_frequencies_by_macd(conn: AsyncIOMotorClient, date: str):

    epoch_date = get_epoch(date)

    document = await conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].find_one(
        {"date": epoch_date},
        {"_id": False, "tickers": True},
    )
    tickers = document["tickers"].split(",")
    log.info(tickers)

    period = 5
    cursor = (
        conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME]
        .find(
            {
                "date": {"$lt": epoch_date}
            },
            {"_id": False, "tickers": True}
        )
        .sort("date", -1)
        .limit(period)
    )

    tickers_in_previous_periods = [
        item["tickers"].split(",") for item in await cursor.to_list(length=period)
    ]
    log.info(tickers_in_previous_periods)

    for ticker in tickers:
        frequency = ""
        for idx, previous_tickers in enumerate(tickers_in_previous_periods):
            if ticker in previous_tickers:
                frequency += f"T-{idx+1}, "

        frequency = frequency[:-2]

        await update_single_ticker(
            conn,
            ticker,
            date,
            {"frequencies": {"macd": frequency}}
        )
