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


async def publish_us_session_v2(
    conn, pool, date_string: str, history_store=None, split_provider=None
) -> dict:
    """Publish a complete v2 snapshot using only incremental local high state."""
    from db.crud.published_archive import STOCK_BOUNCE_V2_ARTIFACT_KEY
    from .adapters import EodhdStockBounceAdapter, PostgresStockBounceHistoryStore
    from .backfill import sanitize_provider_text
    from .history import advance_high_watermark, split_ratio
    from .semantics_v2 import UNIVERSES, build_snapshot_v2

    store = history_store or PostgresStockBounceHistoryStore(pool)
    existing = await store.load_snapshot(date_string)
    if existing is not None:
        coverage = existing["coverage"]
        return {
            "date": date_string,
            "market": "US",
            "artifact_key": STOCK_BOUNCE_V2_ARTIFACT_KEY,
            "rows": len(existing["rows"]),
            "coverage": {key: value["status"] for key, value in coverage.items()},
        }

    cursor = conn[MONGO_DB_NAME]["analytics"].find(
        {"date": get_epoch(date_string), **market_mongo_filter("US")}
    )
    analytics = await cursor.to_list(length=None)
    if not analytics:
        raise ValueError("StockBounce v2 publication requires US analytics rows")
    whole = {str(row["ticker"]).upper() for row in analytics}
    current_macd = {
        str(row["ticker"]).upper() for row in analytics if row.get("macd") is not None
    }
    macd = set(await store.list_macd_tickers(date_string))
    tickers = sorted(whole | macd)
    provider = split_provider or EodhdStockBounceAdapter()
    try:
        bars = await store.load_bars(tickers, date_string)
        watermarks = await store.load_watermarks(tickers)
        intervening = await store.load_bars_after_watermarks(
            tickers, watermarks, date_string
        )
        recovery_dates = sorted(
            {
                missed_bar["date"]
                for missed_bars in intervening.values()
                for missed_bar in missed_bars
            }
        )
        fetched_daily_splits = []
        for split_date in [*recovery_dates, date_string]:
            fetched_daily_splits.append(await provider.fetch_daily_splits(split_date))
        daily_splits = {}
        for fetched in fetched_daily_splits:
            for split in fetched:
                ticker = str(split.get("code", "")).upper()
                if ticker not in tickers:
                    continue
                daily_splits.setdefault(ticker, []).append(
                    {
                        "date": split.get("date", split.get("split_date"))[:10],
                        "ratio": split_ratio(split),
                    }
                )
        for ticker, normalized in daily_splits.items():
            await store.persist_splits(ticker, normalized)
        splits = await store.load_splits(tickers, watermarks, date_string)
        rows = []
        advanced = {}
        exclusions = {universe: 0 for universe in UNIVERSES}
        for ticker in tickers:
            membership = [
                universe
                for universe, members in (
                    ("whole_market", whole),
                    ("macd_history", macd),
                )
                if ticker in members
            ]
            bar = bars.get(ticker)
            watermark = watermarks.get(ticker)
            if bar is None or watermark is None or watermark["date"] >= date_string:
                for universe in membership:
                    exclusions[universe] += 1
                continue
            ticker_splits = splits.get(ticker, [])
            current = watermark
            for missed_bar in sorted(
                intervening.get(ticker, []), key=lambda item: item["date"]
            ):
                _, current = advance_high_watermark(current, missed_bar, ticker_splits)
            previous, next_watermark = advance_high_watermark(
                current, bar, ticker_splits
            )
            if previous is None:
                for universe in membership:
                    exclusions[universe] += 1
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "open": float(bar["open"]),
                    "high": float(bar["high"]),
                    "close": float(bar["close"]),
                    "volume": int(bar["volume"]),
                    "previous_all_time_high": previous,
                    "universes": membership,
                }
            )
            advanced[ticker] = next_watermark
        coverage = {
            "whole_market": {
                "status": "degraded" if exclusions["whole_market"] else "exact",
                "universe_provenance": "mongo_analytics+local_ohlcv",
                "exclusions_count": exclusions["whole_market"],
            },
            "macd_history": {
                "status": "degraded" if exclusions["macd_history"] else "exact",
                "universe_provenance": "recoverable_macd_membership",
                "exclusions_count": exclusions["macd_history"],
            },
        }
        if not rows:
            raise ValueError(
                "StockBounce v2 publication requires verified high history"
            )
        snapshot = build_snapshot_v2(
            date_string,
            rows,
            coverage=coverage,
            max_lookback=await store.max_lookback(date_string),
        )
        await store.publish(
            date_string,
            snapshot,
            advanced,
            current_macd_tickers=current_macd,
        )
    except Exception as error:
        raise RuntimeError(sanitize_provider_text(error)) from None
    return {
        "date": date_string,
        "market": "US",
        "artifact_key": STOCK_BOUNCE_V2_ARTIFACT_KEY,
        "rows": len(rows),
        "coverage": {key: value["status"] for key, value in coverage.items()},
    }
