"""Scheduled compact-state seeding for tickers absent from the initial backfill."""

import asyncio

from core.markets import market_mongo_filter
from core.settings import MONGO_DB_NAME
from utils.handle_datetimes import get_epoch

from .backfill import StockBounceBackfillV2, sanitize_provider_text
from .history import advance_high_watermark


class StockBounceSeederV2:
    """Establish pre-session high watermarks with bounded provider workers."""

    def __init__(
        self,
        store,
        remote_bars,
        retry_attempts: int = 3,
        max_concurrency: int = 4,
    ):
        self.store = store
        self.max_concurrency = max(1, int(max_concurrency))
        self.history = StockBounceBackfillV2(
            store,
            local_bars=None,
            remote_bars=remote_bars,
            retry_attempts=retry_attempts,
            max_concurrency=self.max_concurrency,
        )

    async def run(self, tickers, date_string: str) -> dict:
        """Seed only missing state, leaving target-session evaluation to publication."""
        tickers = sorted({str(ticker).upper() for ticker in tickers})
        watermarks = await self.store.load_watermarks(tickers)
        pending = [ticker for ticker in tickers if watermarks.get(ticker) is None]
        report = {
            "candidates_count": len(pending),
            "seeded_count": 0,
            "no_prior_history_count": 0,
            "failed_count": 0,
            "errors": {},
        }
        queue = asyncio.Queue()
        for ticker in pending:
            queue.put_nowait(ticker)

        async def worker():
            while True:
                try:
                    ticker = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    payload = await self.history.fetch_full_history(ticker, date_string)
                    watermark = None
                    for bar in payload["bars"]:
                        if bar["date"] >= date_string:
                            break
                        _, watermark = advance_high_watermark(
                            watermark, bar, payload["splits"]
                        )
                    if watermark is None:
                        report["no_prior_history_count"] += 1
                    else:
                        await self.store.seed(ticker, watermark, payload["splits"])
                        report["seeded_count"] += 1
                except Exception as error:  # pylint: disable=broad-except
                    report["failed_count"] += 1
                    report["errors"][ticker] = sanitize_provider_text(error)
                finally:
                    queue.task_done()

        if pending:
            await asyncio.gather(
                *(worker() for _ in range(min(self.max_concurrency, len(pending))))
            )
        return report


async def seed_us_session_v2(
    conn,
    pool,
    date_string: str,
    history_store=None,
    remote_bars=None,
    retry_attempts: int = 3,
    max_concurrency: int = 4,
) -> dict:
    """Seed analytics and persisted MACD newcomers before v2 publication."""
    from .adapters import EodhdStockBounceAdapter, PostgresStockBounceHistoryStore

    cursor = conn[MONGO_DB_NAME]["analytics"].find(
        {"date": get_epoch(date_string), **market_mongo_filter("US")}
    )
    analytics = await cursor.to_list(length=None)
    store = history_store or PostgresStockBounceHistoryStore(pool)
    macd_tickers = await store.list_macd_tickers(date_string)
    provider = remote_bars or EodhdStockBounceAdapter()
    seeder = StockBounceSeederV2(
        store,
        provider,
        retry_attempts=retry_attempts,
        max_concurrency=max_concurrency,
    )
    return await seeder.run(
        [row["ticker"] for row in analytics] + macd_tickers,
        date_string,
    )
