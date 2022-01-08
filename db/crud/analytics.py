"""
Methods to handle CRUD operation with analytics collection in the db
"""
from typing import Optional

from db.mongodb import AsyncIOMotorClient
from core.settings import MONGO_DB_NAME
from utils.handle_datetimes import get_epoch
from utils.handle_calculations import get_slope_normalized

MONGO_COLLECTION_NAME = "analytics"


async def get_analytics_by_open_close_change(
    conn: AsyncIOMotorClient,
    n_trading_days: int,
    epoch_date: int,
    query: Optional[str] = "$gt",
) -> list[dict]:
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
                    "lastDayOpenClosePriceChange": {query: 0},
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
        epoc_date = get_epoch(date)

        # getting lists of advanced and declining stocks
        list_num_adv_stocks = await get_analytics_by_open_close_change(
            conn, n_trading_days, epoc_date
        )
        list_num_dec_stocks = await get_analytics_by_open_close_change(
            conn, n_trading_days, epoc_date, "$lt"
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
