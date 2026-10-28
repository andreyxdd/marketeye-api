"""Daily full-universe StockBounce publication from Mongo analytics."""

import asyncio

from core.markets import market_mongo_filter
from core.settings import MONGO_DB_NAME
from db.crud.published_archive import STOCK_BOUNCE_ARTIFACT_KEY, upsert_artifact
from utils.handle_datetimes import get_epoch
from utils.handle_external_apis import get_tickers

from .semantics import build_snapshot


async def publish_us_session(conn, pool, date_string: str) -> dict:
    expected = set(await asyncio.to_thread(get_tickers, date_string, market="US"))
    cursor = conn[MONGO_DB_NAME]["analytics"].find(
        {"date": get_epoch(date_string), **market_mongo_filter("US")}
    )
    rows = await cursor.to_list(length=None)
    by_ticker = {}
    for row in rows:
        by_ticker[row["ticker"].upper()] = {
            **row,
            "open_close_change_pct": float(row["one_day_open_close_change"]) * 100,
        }
    missing = sorted(expected - set(by_ticker))
    if missing:
        raise ValueError(
            "StockBounce publication has incomplete provider coverage: "
            + ", ".join(missing[:20])
        )
    if not expected:
        raise ValueError("StockBounce publication requires a declared US universe")
    snapshot = build_snapshot(
        date_string,
        [by_ticker[ticker] for ticker in sorted(expected)],
        declared_universe_count=len(expected),
    )
    await upsert_artifact(
        pool,
        date_string,
        STOCK_BOUNCE_ARTIFACT_KEY,
        snapshot,
        market="US",
    )
    return {
        "date": date_string,
        "market": "US",
        "artifact_key": STOCK_BOUNCE_ARTIFACT_KEY,
        "rows": len(snapshot["rows"]),
        "coverage": "exact",
    }
