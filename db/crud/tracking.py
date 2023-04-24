"""
Methods to handle CRUD operation with 'analytics' collection in the db
with regard to stock tracking procedure
"""
from typing import Optional
from core.settings import MONGO_DB_NAME
from db.mongodb import AsyncIOMotorClient
from utils.handle_datetimes import get_epoch

MONGO_ANALYTICS_COLLECTION = "analytics"
MONGO_TRACKING_COLLECTION = "tracking"
CRITERIA = [
    "one_day_avg_mf",
    "three_day_avg_mf",
    "volume",
    "three_day_avg_volume",
    "macd",
]


async def put_top_tickers_by_criterion(
    conn: AsyncIOMotorClient, date: str, criterion: str, lim: Optional[int] = 20
):
    """
    Method to retrieve and upsert ticker trackings for a given criterion

    Raises:
      Exception: Method reported an error
    """
    try:
        epoch_date = get_epoch(date)
        cursor = (
            conn[MONGO_DB_NAME][MONGO_ANALYTICS_COLLECTION]
            .find(
                {"date": epoch_date},
                {"_id": False, "ticker": True},
            )
            .sort(criterion, -1)
            .limit(lim)
        )
        tickers = [item["ticker"] for item in await cursor.to_list(length=lim)]

        await conn[MONGO_DB_NAME][MONGO_TRACKING_COLLECTION].update_one(
            {"date": epoch_date, "criterion": criterion},
            {"$set": {"tickers": tickers, "date": epoch_date, "criterion": criterion}},
            upsert=True,
        )
    except Exception as e:  # pylint: disable=W0703
        raise Exception(
            "db/crud/tracking.py, def put_top_tickers_by_criterion: reported an error"
        ) from e


async def put_top_tickers(conn: AsyncIOMotorClient, date: str):
    """
    Method to upsert the ticker tracking documents with different selection criteria

    Raises:
      Exception: Method reported an error
    """
    try:
        for criterion in CRITERIA:
            await put_top_tickers_by_criterion(conn, date, criterion)
        return (
            "db/crud/tracking.py, def put_top_tickers:"
            + "tickers were retrieved and put for tracking"
        )
    except Exception as e:  # pylint: disable=W0703
        raise Exception(
            "db/crud/tracking.py, def put_top_tickers: reported an error"
        ) from e
