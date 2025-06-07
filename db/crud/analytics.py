"""
Methods to handle CRUD operation with 'analytics' collection in the db
"""
import asyncio
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor

from core.settings import MONGO_DB_NAME
from db.crud.tracking import get_analytics_frequencies
from db.mongodb import AsyncIOMotorClient
from db.crud.scrapes import get_mentions
from db.redis import RedisCache
from utils.handle_datetimes import get_date_string, get_epoch, get_last_quater_date
from utils.handle_calculations import get_slope_normalized
from utils.handle_external_apis import (
    get_polygon_tickers,
    get_quarterly_free_cash_flow_polygon,
    get_ticker_base_analytics,
    get_ticker_extra_analytics,
)

MONGO_COLLECTION_NAME = "analytics"

cache = RedisCache()
cache.connect()


async def get_analytics_by_open_close_change(
    conn: AsyncIOMotorClient,
    n_trading_days: int,
    epoch_date: int,
    query: Optional[str] = "$gt",
) -> List[dict]:
    """
    Function to get list of objects as {"_id": (epochDate), "count": (number)} where
    the number of advancing (query="$gt") or declining (query="$lt") is counted.
    The final array sorted by the 'epoch_date' (the "_id" field) in the ascending order.

    Args:
        conn (AsyncIOMotorClient): db-connection string
        n_trading_days (int): period to search for
        epoch_date (int): date in epoch format
        query (Optional[str], optional): query for the aggregation. Defaults to "$gt".

    Raises:
        Exception: Method reported an error

    Returns:
        list[dict]:
            List with the stocks counted by the criterion (query) for each date,
            e.g [{epoch_date (_id): number of stocks found by criterion}]
    """
    try:
        pipeline = [
            {
                "$match": {
                    "date": {"$lte": epoch_date},
                    "one_day_open_close_change": {query: 0},
                }
            },
            {"$unwind": "$date"},
            {"$group": {"_id": "$date", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
        cursor = conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].aggregate(pipeline)
        results = await cursor.to_list(length=n_trading_days)
        return results
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "server/db/crud/analytics.py, def get_analytics_by_open_close_change reported an error"
        ) from e


async def get_normalazied_cvi_slope(
    conn: AsyncIOMotorClient, date: str, n_trading_days: Optional[int] = 50
) -> float:
    """
    Function to compute the slope of Cumulative Volume Index as a
    linear regression over the last 50 trading days from the given date.
    Recal CVI definition by the following link:
    https://www.marketinout.com/technical_analysis.php?t=Cumulative_Volume_Index_(CVI)&id=38

    Args:
        conn (AsyncIOMotorClient): db-connection string
        date (str): starting date
        n_trading_days (Optional[int], optional):
            number of past trading days from the starting date. Defaults to 50.

    Raises:
        Exception:
            list_num_adv_stocks and list_num_dec_stocks should have the
            same size (it is the number of individual tickers)
        Exception:
            the dates should be the same in the lists
        Exception: Method reported an error

    Returns:
        float: nomalized CVI slope
    """
    try:
        epoch_date = get_epoch(date)

        # getting lists of advanced and declining stocks
        list_num_adv_stocks = await get_analytics_by_open_close_change(
            conn, n_trading_days, epoch_date
        )
        list_num_dec_stocks = await get_analytics_by_open_close_change(
            conn, n_trading_days, epoch_date, "$lt"
        )
        counter_length = len(list_num_adv_stocks)

        if counter_length != len(list_num_dec_stocks):
            raise Exception(
                "Number of dates is not equal in the lists of advancing/declining stocks count."
            )

        if list_num_adv_stocks[-1]["_id"] != list_num_dec_stocks[-1]["_id"]:
            raise Exception(
                "The dates in the lists of advancing/declining stocks do not correlate"
            )

        trading_days = []
        cvis = []

        # first elemnt in the array of CVIs:
        cvis.append(list_num_adv_stocks[0]["count"] - list_num_dec_stocks[0]["count"])
        # and trading days array as well
        trading_days.append(1)

        # iterations start with 0
        for i in range(1, counter_length):
            cvis.append(
                cvis[i - 1]
                + list_num_adv_stocks[i]["count"]
                - list_num_dec_stocks[i]["count"]
            )
            trading_days.append(i + 1)

        return get_slope_normalized(trading_days, cvis)

    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "server/db/crud/analytics.py def get_normalazied_CVI_slope reported an error"
        ) from e


async def compute_base_analytics_and_insert(conn: AsyncIOMotorClient, date: str) -> str:
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
    analytics_to_insert = []
    msg = []

    try:
        tickers_to_insert = await get_missing_tickers(conn, date)
        n_tickers = len(tickers_to_insert)

        if tickers_to_insert:

            msg.append(
                "db/crud/analytics.py, def compute_base_analytics_and_insert:"
                + f" The total number of tickers to analyze for {date} (epoch {get_epoch(date)}) is {n_tickers}"
            )
            print(msg[-1])

            for ticker in tickers_to_insert:
                ticker_base_analytics = get_ticker_base_analytics(ticker, date)
                date_str = get_date_string(ticker_base_analytics["date"])
                if date_str is not date:
                    ticker = ticker_base_analytics["ticker"]
                    epoch = ticker_base_analytics["date"]
                    msg.append("db/crud/analytics.py, def compute_base_analytics_and_insert:" + f" The ticker base analytics for ticker {ticker} contains erroneous date {date_str} (epoch {epoch}) while the date-to-insert is {date}")
                    print(msg[-1])
                    continue
                analytics_to_insert.append(ticker_base_analytics)

            analytics_to_insert = list(
                filter(None, analytics_to_insert)
            )  # removing empty objects
            msgResult = f"db/crud/analytics.py, def compute_base_analytics_and_insert: Tickers analytics were computed: total of {len(analytics_to_insert)}"
            if analytics_to_insert[0]:
                analytics_date = analytics_to_insert[0]["date"]
                ticker = analytics_to_insert[0]["ticker"]
                msgResult += f" for {date} (epoch - {analytics_date}, date string {get_date_string(analytics_date)}, ticker {ticker})"
            msg.append(msgResult)
            print(msg[-1])

            if len(analytics_to_insert) > 0:
                response = await conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].insert_many(
                    analytics_to_insert, ordered=False
                )
                msg.append(
                    "db/crud/analytics.py, def compute_base_analytics_and_insert:"
                    + f" Tickers analytics were inserted via {response}"
                )
                print(msg[-1])
        else:
            msg.append(
                "db/crud/analytics.py, def compute_base_analytics_and_insert:"
                + f" No tickers to insert for {date}"
            )
            print(msg[-1])

        return "\n\n".join(msg)
    except Exception as e:  # pylint: disable=W0703
        print("def compute_base_analytics_and_insert reported an error:", {type(e).__name__})
        if type(e).__name__ != "BulkWriteError":
            raise Exception(
                "db/crud/analytics.py, def compute_base_analytics_and_insert: reported an error"
            ) from e

        print(
            "db/crud/analytics.py, def compute_base_analytics_and_insert:"
            + f" Mongodb {type(e).__name__} occured during insert_many() operation."
            + " Still, new base analytics data has been inserted."
        )
        return "\n\n".join(msg)


async def get_analytics_tickers(conn: AsyncIOMotorClient, date: str) -> List[str]:
    """
    Function that returns a list of all the tickers that
    are present in the analytics mongodb collection for the given date

    Args:
        conn (AsyncIOMotorClient): db-connection string
        date (str): date to search for

    Raises:
        Exception: Method reports an error

    Returns:
        list[str]: list of strings (tickers' names)
    """
    try:
        epoch_date = get_epoch(date)
        cursor = await conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].distinct(
            "ticker", {"date": epoch_date}
        )
        return list(cursor)
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "db/crud/analytics.py, def get_analytics_tickers reported an error"
        ) from e


async def get_missing_tickers(conn: AsyncIOMotorClient, date: str) -> List[str]:
    """
    Function that returns a list of tickers that are present in the
    Quandl API response but are missing in the MongoDB analytics collection

    Args:
        conn (AsyncIOMotorClient): db-connection string
        date (str): date to search for

    Raises:
        Exception: Method reports an error

    Returns:
        list[str]: list of strings (missing tickers)
    """
    try:
        # tickers list from quandl
        tickers = get_polygon_tickers(date)

        # tickers list from analytics collection in mongodb
        db_tickers = await get_analytics_tickers(conn, date)
        # array substraction - result is an array
        return list(set(tickers) - set(db_tickers))
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "db/crud/analytics.py, def get_missing_tickers reported an error"
        ) from e


async def remove_base_analytics(
    conn: AsyncIOMotorClient, date: str, collection_name: str = MONGO_COLLECTION_NAME
):
    """
    Function to remove all the stocks base analytics data for the provided date.
    Make sure that provided date is for the 'America/New_York' timezone

    Args:
        conn (AsyncIOMotorClient): db-connection string
        date (str): date IN THE 'America/New_York' TIMEZONE

    Raises:
        Exception: Method reports an error
    """
    try:
        epoch_date = get_epoch(date)
        deleted_docs = await conn[MONGO_DB_NAME][collection_name].delete_many(
            {"date": epoch_date}
        )
        deleted_docs_count = deleted_docs.deleted_count

        if deleted_docs_count > 0:
            print(
                "db/crud/analytics.py, def remove_base_analytics:"
                + f" Successfully removed {deleted_docs_count}"
                + f" documents dated by {date} ({epoch_date})"
            )
        else:
            print(
                "db/crud/analytics.py, def remove_base_analytics:"
                + f" No documents were found for {date} ({epoch_date})"
            )
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "db/crud/analytics.py, def remove_base_analytics reported an error"
        ) from e


@cache.use_cache_async(ignore_first_arg=True)
async def get_analytics_sorted_by(
    conn: AsyncIOMotorClient, date: str, criterion: str, lim: Optional[int] = 20
) -> List[dict]:
    """
    Function to get top 20 stocks by the given criterion

    Args:
        conn (AsyncIOMotorClient): db-connection string
        date (str): date to serach for
        criterion (str): criterion by which to sort analytics
        lim (Optional[int], optional): number of stocks to return. Defaults to 20.

    Raises:
        Exception: Method reports an error

    Returns:
        list[dict]:
            list of dict. See compute_base_analytics and compute_extra_analytics for details
    """
    try:
        epoch_date = get_epoch(date)
        cursor = (
            conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME]
            .find(
                {"date": epoch_date},
                {"_id": False, "bounce": False, "close": False, "open": False},
            )
            .sort(criterion, -1)
            .limit(lim)
        )
        items = await cursor.to_list(length=lim)

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            futures = [
                await loop.run_in_executor(
                    executor, extend_base_analytics, conn, item, criterion
                )
                for item in items
            ]

            return await asyncio.gather(*futures)
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "db/crud/analytics.py, def get_analytics_sorted_by reported an error"
        ) from e


async def get_dates(conn: AsyncIOMotorClient) -> list:
    """
    Function to get all the distinct date from the analytics collection

    Args:
        conn (AsyncIOMotorClient): db-connection string

    Raises:
        Exception: Method reports an error

    Returns:
        list: list of dates in epoch format
    """
    try:
        cursor = await conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].distinct("date")
        return [  # ed - epoch_date
            {"epoch": ed, "date_string": get_date_string(ed)} for ed in list(cursor)
        ]

    except Exception as e:
        print("Error message:", e)
        raise Exception("db/crud/analytics.py, def get_dates reported an error") from e


async def extend_base_analytics(
    conn: AsyncIOMotorClient, base_analytics: dict, criterion: str
):
    """
    Function that extends the provided base_analytics object (see
    output schema for the compute_base_analytics) with extra_analytics
    object (see output schema for the compute_extra_analytics) and
    get_mentions fmethod output

    Args:
        conn (AsyncIOMotorClient): db-connection string
        base_analytics (dict): see output schema for the compute_base_analytics

    Raises:
        Exception: Method reported an error

    Returns:
        dict: combination of returned values from compute_base_analytics,
        compute_extra_analytics, get_mentions
    """
    try:
        ticker = base_analytics["ticker"]
        date = get_date_string(base_analytics["date"])
        quater_date = get_last_quater_date(date)

        return {
            **base_analytics,
            **get_ticker_extra_analytics(ticker, date),
            **await get_mentions(conn, ticker, date),
            "fcf": get_quarterly_free_cash_flow_polygon(ticker, quater_date),
            "frequencies": await get_analytics_frequencies(
                conn, date, criterion, ticker
            ),
        }
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "db/crud/analytics.py, def extend_base_analytics reported an error"
        ) from e
