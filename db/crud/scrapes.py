"""
Methods to handle CRUD operation with 'scrapes' collection in the db
"""
import asyncio

from core.settings import MONGO_DB_NAME
from db.mongodb import AsyncIOMotorClient
from db.redis import use_cache_async
from utils.handle_datetimes import get_epoch, get_past_date

MONGO_COLLECTION_NAME = "scrapes"


async def remove_scrapes(conn: AsyncIOMotorClient, date: str):
    """
    Function to remove all the scrapes data for the given date.
    The passed date should be in the 'America/New_York' timezone

    Args:
        conn (AsyncIOMotorClient): connection string
        date (str): date, 'America/New_York' timezone

    Raises:
        Exception: Method reports an error for some reason
    """
    try:
        deleted_docs = await conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].delete_many(
            {"date": get_epoch(date)}
        )
        deleted_docs_number = deleted_docs.deleted_count

        if deleted_docs_number > 0:
            print(
                "db/crud/scrapes.py, def remove_scrapes:"
                + f" Successfully removed {deleted_docs_number}"
                + f" documents dated by {date} ({get_epoch(date)})"
            )
        else:
            print(
                "db/crud/scrapes.py, def remove_scrapes:"
                + f" No documents were found for {date} ({get_epoch(date)})"
            )
    except Exception as exp:
        print("Error message:", exp)
        raise Exception(
            "db/crud/scrapes.py, def remove_scrapes reported an error"
        ) from exp


@use_cache_async(ignore_first_arg=True)
async def get_mentions(conn: AsyncIOMotorClient, ticker: str, date: str) -> list:
    """
    Function to get mentions counts from the 'scrapes' collection

    Args:
        conn (AsyncIOMotorClient): db-connection string
        date (str): date to serach for
        ticker (str): stock ticker abbreviation

    Raises:
        Exception: Method reports an error

    Returns:
        dict: {
            mentions_over_one_day: number,
            mentions_over_two_days: number,
            mentions_over_three_days: number
        }
    """
    try:
        dates = [date, get_past_date(1, date), get_past_date(2, date)]

        coroutines = []
        for curr_date in dates:
            coroutines.append(
                conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].find_one(
                    {"date": get_epoch(curr_date), "ticker": ticker}
                )
            )

        mentions = []
        mentions_sum = 0
        for res in await asyncio.gather(*coroutines):
            if res and "mentions" in res:
                mentions_sum += res["mentions"]
            mentions.append(mentions_sum)

        return {
            "mentions_over_one_day": mentions[0],
            "mentions_over_two_days": mentions[1],
            "mentions_over_three_days": mentions[2],
        }

    except Exception as e:
        print("Error message:", e)
        raise Exception("db/crud/scrapes.py, def get_mentions reported an error") from e
