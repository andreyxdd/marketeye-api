"""
Methods to handle CRUD operation with 'analytics' collection in the db
with regard to stock tracking procedure
"""
from typing import Optional

from core.markets import DEFAULT_MARKET, market_mongo_filter, normalize_market
from core.settings import MONGO_DB_NAME
from db.mongodb import AsyncIOMotorClient
from utils.handle_datetimes import get_epoch, get_past_date
from utils.handle_external_apis import cache_quaterly_free_cash_flow

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
    conn: AsyncIOMotorClient,
    date: str,
    criterion: str,
    lim: Optional[int] = 20,
    market: str = DEFAULT_MARKET,
):
    try:
        market = normalize_market(market)
        epoch_date = get_epoch(date)
        query = {"date": epoch_date, **market_mongo_filter(market)}
        cursor = (
            conn[MONGO_DB_NAME][MONGO_ANALYTICS_COLLECTION]
            .find(
                query,
                {"_id": False, "ticker": True},
            )
            .sort(criterion, -1)
            .limit(lim)
        )
        tickers = [item["ticker"] for item in await cursor.to_list(length=lim)]

        if tickers:
            await conn[MONGO_DB_NAME][MONGO_TRACKING_COLLECTION].update_one(
                {"date": epoch_date, "criterion": criterion, "market": market},
                {
                    "$set": {
                        "tickers": tickers,
                        "date": epoch_date,
                        "criterion": criterion,
                        "market": market,
                    }
                },
                upsert=True,
            )

        return tickers
    except Exception as e:  # pylint: disable=W0703
        raise Exception(
            "db/crud/tracking.py, def put_top_tickers_by_criterion: reported an error"
        ) from e


async def put_top_tickers(conn: AsyncIOMotorClient, date: str, market: str = DEFAULT_MARKET):
    try:
        for criterion in CRITERIA:
            await put_top_tickers_by_criterion(conn, date, criterion, market=market)
        return (
            "db/crud/tracking.py, def put_top_tickers:"
            + f" tickers were retrieved and set up for tracking ({market})"
        )
    except Exception as e:  # pylint: disable=W0703
        print("Error message:", e)
        raise Exception(
            "db/crud/tracking.py, def put_top_tickers: reported an error"
        ) from e


async def get_analytics_frequencies(
    conn: AsyncIOMotorClient,
    date: str,
    criterion: str,
    ticker: str,
    period: Optional[int] = 25,
    market: str = DEFAULT_MARKET,
):
    try:
        market = normalize_market(market)
        past_date = get_past_date(period, date)
        epoch_past_date = get_epoch(past_date)
        epoch_date = get_epoch(date)
        pipeline = [
            {
                "$match": {
                    "criterion": criterion,
                    **market_mongo_filter(market),
                }
            },
            {
                "$match": {
                    "date": {
                        "$gt": epoch_past_date,
                        "$lt": epoch_date,
                    }
                }
            },
            {"$sort": {"date": -1}},
        ]
        cursor = conn[MONGO_DB_NAME][MONGO_TRACKING_COLLECTION].aggregate(pipeline)
        result = await cursor.to_list(length=period)

        frequencies_str = ""
        for idx, item in enumerate(result):
            if ticker in item["tickers"]:
                frequencies_str += f"T-{idx+1}, "

        return frequencies_str[:-2]
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "db/crud/tracking.py, def get_analytics_frequencies reported an error"
        ) from e
