"""
Methods to handle CRUD operation with 'analytics' collection in the db
"""
from asyncstdlib import lru_cache
from core.settings import MONGO_DB_NAME
from db.mongodb import AsyncIOMotorClient
from utils.handle_datetimes import get_date_string, get_epoch

MONGO_COLLECTION_NAME = "analytics"

AGGREGATE_STAGES = {
    "is-bounce": {"$match": {"bounce": {"$exists": True}}},
    "project": {
        "$project": {
            "_id": False,
            "ticker": True,
            "date": True,
            "open": True,
            "close": True,
            "volume": True,
            "cp_op_precentage_diff": {"$multiply": ["$one_day_open_close_change", 100]},
            "T1": {"$arrayElemAt": ["$bounce", 0]},
            "T2": {"$arrayElemAt": ["$bounce", 1]},
            "T3": {"$arrayElemAt": ["$bounce", 2]},
            "T4": {"$arrayElemAt": ["$bounce", 3]},
            "T5": {"$arrayElemAt": ["$bounce", 4]},
            "T6": {"$arrayElemAt": ["$bounce", 5]},
            "T7": {"$arrayElemAt": ["$bounce", 6]},
            "T8": {"$arrayElemAt": ["$bounce", 7]},
            "T9": {"$arrayElemAt": ["$bounce", 8]},
            "T10": {"$arrayElemAt": ["$bounce", 9]},
            "T11": {"$arrayElemAt": ["$bounce", 10]},
            "T12": {"$arrayElemAt": ["$bounce", 11]},
            "T13": {"$arrayElemAt": ["$bounce", 12]},
            "T14": {"$arrayElemAt": ["$bounce", 13]},
            "T15": {"$arrayElemAt": ["$bounce", 14]},
            "T16": {"$arrayElemAt": ["$bounce", 15]},
            "T17": {"$arrayElemAt": ["$bounce", 16]},
            "T18": {"$arrayElemAt": ["$bounce", 17]},
        },
    },
    "rising-stocks": {
        "$match": {"cp_op_precentage_diff": {"$gt": 0}},
    },
    "long-term-filter": {
        "$match": {
            "$expr": {
                "$and": [
                    {"$gt": ["$cp_op_precentage_diff", "$T1"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T2"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T3"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T4"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T5"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T6"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T7"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T8"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T9"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T10"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T11"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T12"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T13"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T14"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T15"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T16"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T17"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T18"]},
                ]
            }
        }
    },
    "sort-risers": {
        "$sort": {"cp_op_precentage_diff": -1},
    },
    "top-20": {"$limit": 20},
    "select-fields": {
        "$project": {
            "_id": False,
            "ticker": True,
            "date": True,
            "open": True,
            "close": True,
            "volume": True,
            "cp_op_precentage_diff": True,
        }
    },
}


@lru_cache
async def get_bounce_dates(conn: AsyncIOMotorClient) -> list:
    """
    Function to get all the distinct date from the analytics
    collection with existing bounce field

    Args:
        conn (AsyncIOMotorClient): db-connection string

    Raises:
        Exception: Method reports an error

    Returns:
        list: list of dates in epoch format
    """
    try:
        cursor = conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].aggregate(
            [
                AGGREGATE_STAGES["is-bounce"],
                {"$group": {"_id": "$date"}},
                {"$sort": {"_id": 1}},
            ]
        )

        return [  # ed - epoch_date
            {"epoch": ed["_id"], "date_string": get_date_string(ed["_id"])}
            for ed in await cursor.to_list(length=150)
        ]

    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "db/crud/bounce.py, def get_bounce_dates reported an error"
        ) from e


@lru_cache
async def get_bounce_stocks(conn: AsyncIOMotorClient, date: str, period: int) -> list:
    """
    Method that implements the bounce algorithm on close-open prices difference

    Args:
        conn (AsyncIOMotorClient): db-connection string
        date (str): date string
        period (int): number of periods in the past to analyze between (1 and 18)

    Raises:
        Exception: Method reports an error

    Returns:
        list: top 20 stocks selected by the query with their
        respective open/close prices and volumes
    """

    try:
        epoch_date = get_epoch(date)
        is_long_term = period > 4
        possible_stage = (AGGREGATE_STAGES["long-term-filter"],) if is_long_term else ()
        pipeline = [
            {"$match": {"date": epoch_date}},
            {"$match": {f"bounce.{period-1}": {"$lt": 0}}},
            AGGREGATE_STAGES["project"],
            AGGREGATE_STAGES["rising-stocks"],
            *possible_stage,
            AGGREGATE_STAGES["sort-risers"],
            AGGREGATE_STAGES["top-20"],
            AGGREGATE_STAGES["select-fields"],
        ]
        cursor = conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].aggregate(pipeline)

        return await cursor.to_list(length=20)
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "db/crud/bounce.py, def get_bounce_stocks reported an error"
        ) from e


@lru_cache
async def get_tracked_stocks(
    conn: AsyncIOMotorClient, date: str, tickers: list[str]
) -> list:
    """
    Method that returns stock that are required to be tracked as pre bounce analysis

    Args:
        conn (AsyncIOMotorClient): db-connection string
        date (str): date string
        tickers (list[str]): tickers to track

    Raises:
        Exception: Method reports an error

    Returns:
        list: 20 stocks tickers with their
        respective open/close prices and volumes
    """

    try:
        epoch_date = get_epoch(date)

        pipeline = [
            {"$match": {"date": epoch_date}},
            {"$match": {"ticker": {"$in": tickers}}},
            {
                "$project": {
                    "_id": False,
                    "ticker": True,
                    "date": True,
                    "open": True,
                    "close": True,
                    "volume": True,
                    "cp_op_precentage_diff": {
                        "$multiply": ["$one_day_open_close_change", 100]
                    },
                    "preserveOrder": {
                        "$indexOfArray": [tickers, "$ticker"],
                    },
                }
            },
            {"$sort": {"preserveOrder": 1}},
        ]
        cursor = conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].aggregate(pipeline)
        return await cursor.to_list(length=20)
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "db/crud/bounce.py, def get_tracked_stocks reported an error"
        ) from e
