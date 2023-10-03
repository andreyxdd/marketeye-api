"""
Methods to handle CRUD operation with 'analytics' collection in the db
"""
import asyncio
import logging
from time import sleep
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.settings import MONGO_DB_NAME, QUANDL_RATE_LIMIT, QUANDL_SLEEP_MINUTES
from db.crud.tracking import get_analytics_frequencies
from db.mongodb import AsyncIOMotorClient
from db.crud.scrapes import get_mentions
from db.redis import use_cache_async
from db.retrieve.timeseries import get_timeseries_tickers
from utils.handle_datetimes import get_date_string, get_epoch, get_last_quater_date
from utils.handle_calculations import get_slope_normalized
from utils.quandl import get_single_ticker_analytics, get_quandl_tickers

MONGO_COLLECTION_NAME = "timeseries"

log = logging.getLogger(__name__)


async def update_single_ticker(conn: AsyncIOMotorClient, ticker: str, date: str, data):
    epoch_date = get_epoch(date)
    await conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].update_one(
        {"date": epoch_date, "ticker": ticker},
        {"$set": data}
    )


async def get_missing_tickers(conn: AsyncIOMotorClient, date: str) -> "list[str]":
    """
    Function that returns a list of tickers that are present in the
    Quandl API response but are missing in the MongoDB analytics collection

    Args:
        conn (AsyncIOMotorClient): db-connection string
        date (str): date to search for

    Returns:
        list[str]: list of strings (missing tickers)
    """
    quandl_tickers = get_quandl_tickers(date)[:20]
    db_tickers = await get_timeseries_tickers(conn, date)
    return list(set(quandl_tickers) - set(db_tickers))


async def compute_timeseries_and_insert(conn: AsyncIOMotorClient, date: str) -> str:
    """
    Function to compute analytics for the given EOD data for the tickers
    present in the Quandl database for the given date

    Args:
        conn (AsyncIOMotorClient): db-connection string
        date (str): starting date, for which to compute and insert data

    Raises:
        Exception: Any error occured except MongoDB "BulkWriteError"

    Returns:
        str: report message (with line breaks)
    """
    documents_to_insert = []
    msg = []

    try:
        tickers_to_insert = await get_missing_tickers(conn, date)
        n_tickers = len(tickers_to_insert)

        #################################
        ### CAREFUL! HARDCODING BELOW ###
        #################################

        # Quandl API has a limit: 5000 calls per 10 minutes
        # if the list of tickers is more than 5000 it is divided accrodingly
        partitions = []
        if n_tickers >= QUANDL_RATE_LIMIT:
            while len(tickers_to_insert) >= QUANDL_RATE_LIMIT:
                partial_tickers_to_insert = tickers_to_insert[:QUANDL_RATE_LIMIT]

                # this changes length:
                tickers_to_insert = tickers_to_insert[
                    QUANDL_RATE_LIMIT:
                ]

                partitions.append(partial_tickers_to_insert)

            # adding left overs:
            partitions.append(tickers_to_insert)
        else:
            partitions.append(tickers_to_insert)

        #################################
        #################################
        #################################

        if tickers_to_insert:

            msg.append(
                f"The total number of tickers to analyze is {n_tickers}"
            )
            log.info(msg[-1])

            for partition in partitions:

                # set timeout for 10 minutes to prevent exceeding rate limit of API calls
                if n_tickers > QUANDL_RATE_LIMIT:
                    log.info(
                        "\n--------------------------------------------------------------------"
                    )
                    log.info(
                        " Sleeping for 10 minutes to prevent exceeding Quandl API rate limit"
                    )
                    log.info(
                        "--------------------------------------------------------------------\n"
                    )
                    sleep(QUANDL_SLEEP_MINUTES * 60 + 0.5)

                # getting base analytics for the list of
                # tickers in the current partition
                with ThreadPoolExecutor() as executor:
                    future_list = [
                        executor.submit(
                            get_single_ticker_analytics, ticker, date)
                        for ticker in partition
                    ]

                    for future in as_completed(future_list):
                        documents_to_insert.append(future.result())

            documents_to_insert = list(
                filter(None, documents_to_insert)
            )  # removing empty objects

            msg.append(
                f"Tickers analytics were computed: total of {len(documents_to_insert)}"
            )
            log.info(msg[-1])

            if(documents_to_insert):
                await conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].insert_many(
                    documents_to_insert, ordered=False
                )
                msg.append("Tickers analytics were successfully inserted")
                log.info(msg[-1])
        else:
            msg.append(f"No tickers to insert for {date}")
            log.info(msg[-1])

        return "\n\n".join(msg)
    except Exception as e:  # pylint: disable=W0703
        log.error("Error message:", e)
        if type(e).__name__ != "BulkWriteError":
            raise Exception(
                "db/crud/analytics.py, def compute_base_analytics_and_insert: reported an error"
            ) from e

        log.error(
            "db/crud/analytics.py, def compute_base_analytics_and_insert:"
            + f" Mongodb {type(e).__name__} occured during insert_many() operation."
            + "Still, new base analytics data has been inserted."
        )
