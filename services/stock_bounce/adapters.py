"""Strict local and EODHD range adapters plus PostgreSQL backfill checkpoints."""

import asyncio
import json
import uuid
from datetime import date

from core.settings import EODHD_API_KEY
from db.crud.published_archive import STOCK_BOUNCE_ARTIFACT_KEY
from providers.eodhd_to import EODHD_BASE_URL
from providers.eodhd_us import EodhdUSProvider

from .backfill import LocalBarsResult


class PostgresLocalBarsAdapter:
    def __init__(self, pool):
        self.pool = pool

    async def fetch(self, ticker: str, start_date: str, end_date: str) -> LocalBarsResult:
        try:
            async with self.pool.acquire() as conn:
                records = await conn.fetch(
                    """
                    SELECT session_date, open, high, low, close, volume
                    FROM ohlcv_bars
                    WHERE market = 'US' AND ticker = $1
                      AND session_date BETWEEN $2 AND $3
                    ORDER BY session_date ASC
                    """,
                    ticker,
                    date.fromisoformat(start_date),
                    date.fromisoformat(end_date),
                )
            bars = [
                {
                    "ticker": ticker,
                    "date": record["session_date"].isoformat(),
                    "open": float(record["open"]),
                    "high": float(record["high"]),
                    "low": float(record["low"]),
                    "close": float(record["close"]),
                    "volume": int(record["volume"]),
                }
                for record in records
            ]
            return LocalBarsResult(status="complete", bars=bars)
        except Exception as error:  # pylint: disable=broad-except
            return LocalBarsResult(status="storage_error", bars=[], error=str(error))


class EodhdStockBounceAdapter:
    def __init__(self, provider=None):
        self.provider = provider or EodhdUSProvider()

    async def current_universe(self) -> list[str]:
        return await asyncio.to_thread(self.provider.fetch_ticker_universe, "")

    async def fetch_range(self, ticker: str, start_date: str, end_date: str) -> list[dict]:
        def fetch():
            response = self.provider._http_get(  # pylint: disable=protected-access
                f"{EODHD_BASE_URL}/eod/{ticker}.US"
                f"?from={start_date}&to={end_date}&api_token={EODHD_API_KEY}&fmt=json"
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError(f"EODHD returned invalid bars for {ticker}")
            return [
                {
                    "ticker": ticker,
                    "date": bar["date"],
                    "open": float(bar["open"]),
                    "high": float(bar["high"]),
                    "low": float(bar["low"]),
                    "close": float(bar["close"]),
                    "volume": int(bar["volume"]),
                }
                for bar in payload
            ]

        return await asyncio.to_thread(fetch)


class PostgresBackfillStore:
    def __init__(self, pool):
        self.pool = pool

    async def create_run(self, resume_run_id=None):
        run_id = resume_run_id or str(uuid.uuid4())
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stock_bounce_backfill_runs(run_id, status)
                VALUES($1, 'running')
                ON CONFLICT(run_id) DO UPDATE SET status = 'running', updated_at = NOW()
                """,
                run_id,
            )
        return run_id

    async def list_targets(self, force=False):
        del force
        async with self.pool.acquire() as conn:
            records = await conn.fetch(
                """
                SELECT d.session_date, array_agg(t.ticker ORDER BY t.ticker) AS tickers,
                       EXISTS (
                           SELECT 1 FROM published_artifacts a
                           WHERE a.session_date = d.session_date AND a.market = d.market
                             AND a.artifact_key = $1
                             AND a.payload->'coverage'->>'status' IN ('exact', 'degraded')
                       ) AS snapshot_complete
                FROM published_dates d
                JOIN published_tickers t ON t.session_date = d.session_date
                    AND t.market = d.market
                WHERE d.market = 'US'
                  AND EXISTS (
                      SELECT 1 FROM published_artifacts market_artifact
                      WHERE market_artifact.session_date = d.session_date
                        AND market_artifact.market = d.market
                        AND market_artifact.artifact_key = 'market_analytics'
                  )
                GROUP BY d.session_date
                ORDER BY d.session_date ASC
                """,
                STOCK_BOUNCE_ARTIFACT_KEY,
            )
        return [
            {
                "date": record["session_date"].isoformat(),
                "tickers": list(record["tickers"]),
                "snapshot_complete": record["snapshot_complete"],
            }
            for record in records
        ]

    async def completed_ranges(self, run_id):
        async with self.pool.acquire() as conn:
            records = await conn.fetch(
                """
                SELECT ticker, start_date, end_date
                FROM stock_bounce_backfill_ranges
                WHERE run_id = $1 AND status = 'complete'
                """,
                run_id,
            )
        return {
            (
                record["ticker"],
                record["start_date"].isoformat(),
                record["end_date"].isoformat(),
            )
            for record in records
        }

    async def get_range(self, ticker, start_date, end_date):
        result = await PostgresLocalBarsAdapter(self.pool).fetch(
            ticker, start_date, end_date
        )
        if result.status == "storage_error":
            raise RuntimeError(result.error)
        return result.bars

    async def record_range(self, run_id, ticker, start_date, end_date, bars):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(
                    """
                    INSERT INTO ohlcv_bars(
                        market, ticker, session_date, open, high, low, close, volume
                    ) VALUES('US', $1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT(market, ticker, session_date) DO UPDATE SET
                        open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                        close = EXCLUDED.close, volume = EXCLUDED.volume,
                        fetched_at = NOW()
                    """,
                    [
                        (
                            ticker,
                            date.fromisoformat(bar["date"]),
                            bar["open"],
                            bar["high"],
                            bar["low"],
                            bar["close"],
                            bar["volume"],
                        )
                        for bar in bars
                    ],
                )
                await conn.execute(
                    """
                    INSERT INTO stock_bounce_backfill_ranges(
                        run_id, ticker, start_date, end_date, status
                    ) VALUES($1, $2, $3, $4, 'complete')
                    ON CONFLICT(run_id, ticker, start_date, end_date)
                    DO UPDATE SET status = 'complete', fetched_at = NOW()
                    """,
                    run_id,
                    ticker,
                    date.fromisoformat(start_date),
                    date.fromisoformat(end_date),
                )

    async def publish_snapshot(self, run_id, date_string, snapshot):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO published_artifacts(session_date, market, artifact_key, payload)
                    VALUES($1, 'US', $2, $3::jsonb)
                    ON CONFLICT(session_date, market, artifact_key)
                    DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()
                    """,
                    date.fromisoformat(date_string),
                    STOCK_BOUNCE_ARTIFACT_KEY,
                    json.dumps(snapshot),
                )
                await conn.execute(
                    """
                    INSERT INTO stock_bounce_backfill_targets(run_id, session_date, status)
                    VALUES($1, $2, 'complete')
                    ON CONFLICT(run_id, session_date) DO UPDATE SET
                        status = 'complete', error = NULL, updated_at = NOW()
                    """,
                    run_id,
                    date.fromisoformat(date_string),
                )

    async def target_complete(self, run_id, date_string):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM stock_bounce_backfill_targets
                WHERE run_id = $1 AND session_date = $2 AND status = 'complete'
                """,
                run_id,
                date.fromisoformat(date_string),
            )
        return row is not None

    async def finish_run(self, run_id, report):
        status = "complete" if not report["unpublished"] else "incomplete"
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE stock_bounce_backfill_runs
                SET status = $2, report = $3::jsonb, updated_at = NOW()
                WHERE run_id = $1
                """,
                run_id,
                status,
                json.dumps(report),
            )
