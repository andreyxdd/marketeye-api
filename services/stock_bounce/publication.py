"""Daily full-universe StockBounce publication from Mongo analytics."""

from core.markets import market_mongo_filter
from core.settings import MONGO_DB_NAME
from db.crud.published_archive import STOCK_BOUNCE_ARTIFACT_KEY, upsert_artifact
from utils.handle_datetimes import get_epoch

from .semantics import build_snapshot


async def publish_us_session(conn, pool, date_string: str) -> dict:
    # Universe = ingested analytics rows (legacy bounce parity); ingest already
    # skips symbols with short history, no bar for the session, or provider errors.
    cursor = conn[MONGO_DB_NAME]["analytics"].find(
        {"date": get_epoch(date_string), **market_mongo_filter("US")}
    )
    rows = await cursor.to_list(length=None)
    if not rows:
        raise ValueError("StockBounce publication requires US analytics rows")
    snapshot = build_snapshot(
        date_string,
        [
            {
                "ticker": row["ticker"].upper(),
                "open": row["open"],
                "close": row["close"],
                "volume": row["volume"],
                "bounce": row["bounce"],
                "open_close_change_pct": float(row["one_day_open_close_change"]) * 100,
            }
            for row in rows
            # zero-open bars store a null change / no vector; legacy screen never matched them
            if row.get("bounce") is not None
            and row.get("one_day_open_close_change") is not None
        ],
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
