"""
Methods to handle CRUD operation with 'analytics' collection in the db
"""
import asyncio
from typing import Awaitable, Callable, Optional, List

from core.markets import DEFAULT_MARKET, market_mongo_filter, normalize_market
from core.settings import MONGO_DB_NAME
from db.mongodb import AsyncIOMotorClient
from db.redis import RedisCache
from utils.handle_datetimes import get_date_string, get_epoch
from utils.handle_calculations import get_slope_normalized
from utils.handle_external_apis import get_tickers

MONGO_COLLECTION_NAME = "analytics"

cache = RedisCache()
cache.connect()


async def get_adv_dec_counts_by_date(
    conn: AsyncIOMotorClient,
    n_trading_days: int,
    epoch_date: int,
    market: str = "US",
) -> List[dict]:
    """Return per-date adv/dec counts in one aggregation (aligned dates)."""
    try:
        pipeline = [
            {
                "$match": {
                    **market_mongo_filter(market),
                    "date": {"$lte": epoch_date},
                    "one_day_open_close_change": {"$exists": True},
                }
            },
            {
                "$group": {
                    "_id": "$date",
                    "adv": {
                        "$sum": {
                            "$cond": [
                                {"$gt": ["$one_day_open_close_change", 0]},
                                1,
                                0,
                            ]
                        }
                    },
                    "dec": {
                        "$sum": {
                            "$cond": [
                                {"$lt": ["$one_day_open_close_change", 0]},
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
            {"$match": {"$expr": {"$gt": [{"$add": ["$adv", "$dec"]}, 0]}}},
            {"$sort": {"_id": 1}},
        ]
        cursor = conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].aggregate(pipeline)
        results = await cursor.to_list(length=n_trading_days)
        if len(results) > n_trading_days:
            return results[-n_trading_days:]
        return results
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "server/db/crud/analytics.py, def get_adv_dec_counts_by_date reported an error"
        ) from e


async def get_analytics_by_open_close_change(
    conn: AsyncIOMotorClient,
    n_trading_days: int,
    epoch_date: int,
    query: Optional[str] = "$gt",
    market: str = "US",
) -> List[dict]:
    try:
        pipeline = [
            {
                "$match": {
                    **market_mongo_filter(market),
                    "date": {"$lte": epoch_date},
                    "one_day_open_close_change": {query: 0},
                }
            },
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
    try:
        epoch_date = get_epoch(date)
        daily_counts = await get_adv_dec_counts_by_date(
            conn, n_trading_days, epoch_date, market="US"
        )
        if not daily_counts:
            raise Exception(
                "No advancing/declining stock counts found for CVI calculation."
            )

        trading_days = []
        cvis = []
        cvis.append(daily_counts[0]["adv"] - daily_counts[0]["dec"])
        trading_days.append(1)

        for i in range(1, len(daily_counts)):
            cvis.append(
                cvis[i - 1]
                + daily_counts[i]["adv"]
                - daily_counts[i]["dec"]
            )
            trading_days.append(i + 1)

        return get_slope_normalized(trading_days, cvis)

    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "server/db/crud/analytics.py def get_normalazied_CVI_slope reported an error"
        ) from e


async def insert_analytics_batch(
    conn: AsyncIOMotorClient, docs: List[dict], batch_size: int = 500
) -> int:
    from pymongo.errors import BulkWriteError

    inserted = 0
    for start in range(0, len(docs), batch_size):
        batch = docs[start : start + batch_size]
        try:
            response = await conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].insert_many(
                batch, ordered=False
            )
            inserted += len(response.inserted_ids)
        except BulkWriteError as e:
            batch_inserted = e.details.get("nInserted", 0)
            inserted += batch_inserted
            write_errors = e.details.get("writeErrors", [])
            duplicate_count = sum(
                1 for err in write_errors if err.get("code") == 11000
            )
            print(
                "db/crud/analytics.py insert_analytics_batch:"
                f" BulkWriteError during batch insert;"
                f" nInserted={batch_inserted}, duplicate_errors={duplicate_count},"
                f" total_write_errors={len(write_errors)}"
            )
        except Exception as e:
            print("Error message:", e)
            raise
    return inserted


async def compute_base_analytics_and_insert(
    conn: AsyncIOMotorClient, date: str, market: str = DEFAULT_MARKET
) -> str:
    from services.analytics_service import ingest_base_analytics_for_market

    return await ingest_base_analytics_for_market(conn, date, market=market)


async def get_analytics_tickers(
    conn: AsyncIOMotorClient, date: str, market: str = DEFAULT_MARKET
) -> List[str]:
    try:
        epoch_date = get_epoch(date)
        query = {"date": epoch_date, **market_mongo_filter(market)}
        cursor = await conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].distinct(
            "ticker", query
        )
        return list(cursor)
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "db/crud/analytics.py, def get_analytics_tickers reported an error"
        ) from e


async def get_missing_tickers(
    conn: AsyncIOMotorClient, date: str, market: str = DEFAULT_MARKET
) -> List[str]:
    try:
        market = normalize_market(market)
        tickers = get_tickers(date, market=market)
        db_tickers = await get_analytics_tickers(conn, date, market=market)
        return list(set(tickers) - set(db_tickers))
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "db/crud/analytics.py, def get_missing_tickers reported an error"
        ) from e


async def remove_base_analytics(
    conn: AsyncIOMotorClient,
    date: str,
    collection_name: str = MONGO_COLLECTION_NAME,
    market: str = DEFAULT_MARKET,
):
    try:
        epoch_date = get_epoch(date)
        query = {"date": epoch_date, **market_mongo_filter(market)}
        deleted_docs = await conn[MONGO_DB_NAME][collection_name].delete_many(query)
        deleted_docs_count = deleted_docs.deleted_count

        if deleted_docs_count > 0:
            print(
                "db/crud/analytics.py, def remove_base_analytics:"
                + f" Successfully removed {deleted_docs_count}"
                + f" documents for {market} dated by {date} ({epoch_date})"
            )
        else:
            print(
                "db/crud/analytics.py, def remove_base_analytics:"
                + f" No documents were found for {market} on {date} ({epoch_date})"
            )
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "db/crud/analytics.py, def remove_base_analytics reported an error"
        ) from e


async def get_analytics_sorted_by(
    conn: AsyncIOMotorClient,
    date: str,
    criterion: str,
    lim: Optional[int] = 20,
    market: str = DEFAULT_MARKET,
    enrich_fn: Optional[Callable[..., Awaitable[dict]]] = None,
    min_close: Optional[float] = None,
    max_close: Optional[float] = None,
    include_close: bool = False,
) -> List[dict]:
    try:
        if enrich_fn is None:
            from services.analytics_service import enrich_ticker_row

            enrich_fn = enrich_ticker_row

        epoch_date = get_epoch(date)
        query = {"date": epoch_date, **market_mongo_filter(market)}
        close_filter: dict = {"close": {"$exists": True, "$ne": None}}
        if min_close is not None:
            close_filter["close"]["$gte"] = min_close
        if max_close is not None:
            close_filter["close"]["$lte"] = max_close
        if min_close is not None or max_close is not None:
            query.update(close_filter)

        projection = {"_id": False, "bounce": False, "open": False}
        if not include_close:
            projection["close"] = False

        cursor = (
            conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME]
            .find(
                query,
                projection,
            )
            .sort(criterion, -1)
            .limit(lim)
        )
        items = await cursor.to_list(length=lim)

        return await asyncio.gather(
            *[enrich_fn(conn, item, criterion, market=market) for item in items]
        )
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "db/crud/analytics.py, def get_analytics_sorted_by reported an error"
        ) from e


async def get_dates(conn: AsyncIOMotorClient, market: str = DEFAULT_MARKET) -> list:
    try:
        pipeline = [
            {"$match": market_mongo_filter(market)},
            {"$group": {"_id": "$date"}},
            {"$sort": {"_id": 1}},
        ]
        cursor = conn[MONGO_DB_NAME][MONGO_COLLECTION_NAME].aggregate(pipeline)
        epochs = [doc["_id"] for doc in await cursor.to_list(length=10000)]
        return [{"epoch": ed, "date_string": get_date_string(ed)} for ed in epochs]

    except Exception as e:
        print("Error message:", e)
        raise Exception("db/crud/analytics.py, def get_dates reported an error") from e
