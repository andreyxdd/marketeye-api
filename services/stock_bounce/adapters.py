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

    async def fetch(
        self, ticker: str, start_date: str, end_date: str
    ) -> LocalBarsResult:
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

    async def fetch_range(
        self, ticker: str, start_date: str, end_date: str
    ) -> list[dict]:
        def fetch():
            from_param = f"&from={start_date}" if start_date else ""
            response = self.provider._http_get(  # pylint: disable=protected-access
                f"{EODHD_BASE_URL}/eod/{ticker}.US"
                f"?to={end_date}{from_param}&api_token={EODHD_API_KEY}&fmt=json"
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

    async def fetch_splits(self, ticker: str) -> list[dict]:
        def fetch():
            response = self.provider._http_get(  # pylint: disable=protected-access
                f"{EODHD_BASE_URL}/splits/{ticker}.US"
                f"?api_token={EODHD_API_KEY}&fmt=json"
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError(f"EODHD returned invalid splits for {ticker}")
            return payload

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

    async def list_targets(self):
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


class PostgresStockBounceHistoryStore:
    """Batched local state access and atomic daily v2 publication."""

    def __init__(self, pool):
        self.pool = pool

    async def list_macd_tickers(self, before_date):
        async with self.pool.acquire() as conn:
            records = await conn.fetch(
                """
                SELECT ticker FROM stock_bounce_v2_memberships
                WHERE market = 'US' AND universe = 'macd_history'
                  AND first_seen_date < $1
                ORDER BY ticker
                """,
                date.fromisoformat(before_date),
            )
        return [record["ticker"] for record in records]

    async def load_bars(self, tickers, date_string):
        if not tickers:
            return {}
        async with self.pool.acquire() as conn:
            records = await conn.fetch(
                """
                SELECT ticker, session_date, open, high, low, close, volume
                FROM ohlcv_bars
                WHERE market = 'US' AND ticker = ANY($1::text[])
                  AND session_date = $2
                """,
                list(tickers),
                date.fromisoformat(date_string),
            )
        return {
            record["ticker"]: {
                "ticker": record["ticker"],
                "date": record["session_date"].isoformat(),
                "open": float(record["open"]),
                "high": float(record["high"]),
                "low": float(record["low"]),
                "close": float(record["close"]),
                "volume": int(record["volume"]),
            }
            for record in records
        }

    async def load_watermarks(self, tickers):
        if not tickers:
            return {}
        async with self.pool.acquire() as conn:
            records = await conn.fetch(
                """
                SELECT ticker, as_of_date, high
                FROM stock_bounce_v2_high_watermarks
                WHERE market = 'US' AND ticker = ANY($1::text[])
                """,
                list(tickers),
            )
        return {
            record["ticker"]: {
                "date": record["as_of_date"].isoformat(),
                "high": float(record["high"]),
            }
            for record in records
        }

    async def load_splits(self, tickers, watermarks, through_date):
        del watermarks
        if not tickers:
            return {}
        async with self.pool.acquire() as conn:
            records = await conn.fetch(
                """
                SELECT ticker, split_date, ratio
                FROM stock_bounce_v2_splits
                WHERE market = 'US' AND ticker = ANY($1::text[])
                  AND split_date <= $2
                ORDER BY ticker, split_date
                """,
                list(tickers),
                date.fromisoformat(through_date),
            )
        result = {ticker: [] for ticker in tickers}
        for record in records:
            result[record["ticker"]].append(
                {
                    "date": record["split_date"].isoformat(),
                    "ratio": float(record["ratio"]),
                }
            )
        return result

    async def max_lookback(self, date_string):
        async with self.pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM published_artifacts
                WHERE market = 'US' AND artifact_key = 'stock_bounce:v2'
                  AND session_date < $1 AND payload->>'schema_version' = '2'
                """,
                date.fromisoformat(date_string),
            )
        return min(1260, int(count))

    async def publish(self, date_string, snapshot, watermarks):
        from db.crud.published_archive import STOCK_BOUNCE_V2_ARTIFACT_KEY

        session_date = date.fromisoformat(date_string)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO published_dates(session_date, market) VALUES($1, 'US')
                    ON CONFLICT(session_date, market) DO NOTHING
                    """,
                    session_date,
                )
                await conn.execute(
                    """
                    INSERT INTO published_artifacts(session_date, market, artifact_key, payload)
                    VALUES($1, 'US', $2, $3::jsonb)
                    ON CONFLICT(session_date, market, artifact_key) DO UPDATE SET
                        payload = EXCLUDED.payload, updated_at = NOW()
                    """,
                    session_date,
                    STOCK_BOUNCE_V2_ARTIFACT_KEY,
                    json.dumps(snapshot),
                )
                await conn.executemany(
                    """
                    INSERT INTO stock_bounce_v2_high_watermarks(
                        market, ticker, as_of_date, high
                    ) VALUES('US', $1, $2, $3)
                    ON CONFLICT(market, ticker) DO UPDATE SET
                        as_of_date = EXCLUDED.as_of_date, high = EXCLUDED.high,
                        updated_at = NOW()
                    """,
                    [
                        (
                            ticker,
                            date.fromisoformat(value["date"]),
                            value["high"],
                        )
                        for ticker, value in watermarks.items()
                    ],
                )
                membership_rows = [
                    (ticker, universe, session_date, session_date)
                    for row in snapshot["rows"]
                    for ticker, universes in ((row["ticker"], row["universes"]),)
                    for universe in universes
                ]
                if membership_rows:
                    await conn.executemany(
                        """
                        INSERT INTO stock_bounce_v2_memberships(
                            market, ticker, universe, first_seen_date, last_seen_date
                        ) VALUES('US', $1, $2, $3, $4)
                        ON CONFLICT(market, ticker, universe) DO UPDATE SET
                            first_seen_date = LEAST(
                                stock_bounce_v2_memberships.first_seen_date,
                                EXCLUDED.first_seen_date
                            ),
                            last_seen_date = GREATEST(
                                stock_bounce_v2_memberships.last_seen_date,
                                EXCLUDED.last_seen_date
                            )
                        """,
                        membership_rows,
                    )


class PostgresBackfillStoreV2:
    """PostgreSQL targets, estimates, compact bars, and temporary v2 checkpoints."""

    def __init__(self, pool):
        self.pool = pool

    async def list_targets(self, since):
        async with self.pool.acquire() as conn:
            records = await conn.fetch(
                """
                SELECT d.session_date, source.payload,
                       EXISTS (
                           SELECT 1 FROM published_artifacts existing
                           WHERE existing.session_date = d.session_date
                             AND existing.market = 'US'
                             AND existing.artifact_key = 'stock_bounce:v2'
                             AND existing.payload->>'schema_version' = '2'
                       ) AS snapshot_complete,
                       LEAST(1260, (
                           SELECT COUNT(*) FROM published_artifacts prior
                           WHERE prior.market = 'US' AND prior.artifact_key = 'stock_bounce:v2'
                             AND prior.session_date < d.session_date
                             AND prior.payload->>'schema_version' = '2'
                       ))::int AS max_lookback,
                       COALESCE((
                           SELECT array_agg(DISTINCT history.row->>'ticker' ORDER BY history.row->>'ticker')
                           FROM published_artifacts prior_source
                           CROSS JOIN LATERAL jsonb_array_elements(
                               prior_source.payload->'rows'
                           ) AS history(row)
                           WHERE prior_source.market = 'US'
                             AND prior_source.artifact_key = 'stock_bounce:v1'
                             AND prior_source.session_date < d.session_date
                       ), ARRAY[]::text[]) AS macd_tickers
                FROM published_dates d
                JOIN published_artifacts source
                  ON source.session_date = d.session_date AND source.market = 'US'
                 AND source.artifact_key = 'stock_bounce:v1'
                WHERE d.market = 'US' AND d.session_date >= $1
                  AND EXISTS (
                      SELECT 1 FROM published_artifacts market_artifact
                      WHERE market_artifact.session_date = d.session_date
                        AND market_artifact.market = 'US'
                        AND market_artifact.artifact_key = 'market_analytics'
                  )
                ORDER BY d.session_date ASC
                """,
                date.fromisoformat(since),
            )
        targets = []
        for record in records:
            payload = record["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            degraded = payload.get("coverage", {}).get("status") == "degraded"
            targets.append(
                {
                    "date": record["session_date"].isoformat(),
                    "tickers": [row["ticker"] for row in payload.get("rows", [])],
                    "macd_tickers": list(record["macd_tickers"]),
                    "snapshot_complete": record["snapshot_complete"],
                    "max_lookback": record["max_lookback"],
                    "estimated": degraded,
                    "whole_market_provenance": "archived_tickers+local_ohlcv",
                    "macd_history_provenance": "recoverable_macd_membership",
                }
            )
        return targets

    async def estimate_storage(self, targets, storage_limit_bytes):
        del storage_limit_bytes
        tickers = {
            ticker
            for target in targets
            for ticker in set(target["tickers"]) | set(target.get("macd_tickers", []))
        }
        async with self.pool.acquire() as conn:
            current = int(
                await conn.fetchval("SELECT pg_database_size(current_database())")
            )
            artifact_bytes = int(
                await conn.fetchval(
                    "SELECT pg_total_relation_size('published_artifacts')"
                )
            )
            bar_bytes = int(
                await conn.fetchval("SELECT pg_relation_size('ohlcv_bars')")
            )
            checkpoint_bytes = int(
                await conn.fetchval(
                    "SELECT pg_total_relation_size('stock_bounce_backfill_ranges')"
                )
            ) + int(
                await conn.fetchval(
                    "SELECT pg_total_relation_size('stock_bounce_v2_backfill_ranges')"
                )
            )
            index_bytes = int(
                await conn.fetchval("SELECT pg_indexes_size('published_artifacts')")
            ) + int(await conn.fetchval("SELECT pg_indexes_size('ohlcv_bars')"))
            average_snapshot = float(
                await conn.fetchval(
                    """
                    SELECT COALESCE(AVG(pg_column_size(payload)), 65536)
                    FROM published_artifacts WHERE artifact_key = 'stock_bounce:v1'
                    """
                )
            )
        artifact_increment = int(len(targets) * average_snapshot * 1.5)
        bar_increment = len(tickers) * 1260 * 128
        checkpoint_increment = len(tickers) * 2 * 1024 * 1024
        index_increment = int((artifact_increment + bar_increment) * 0.4)
        projected = current + (
            artifact_increment + bar_increment + checkpoint_increment + index_increment
        )
        return {
            "current_bytes": current,
            "projected_bytes": projected,
            "components": {
                "v1_v2_artifacts": {
                    "current_bytes": artifact_bytes,
                    "projected_bytes": artifact_bytes + artifact_increment,
                },
                "bars": {
                    "current_bytes": bar_bytes,
                    "projected_bytes": bar_bytes + bar_increment,
                },
                "indexes": {
                    "current_bytes": index_bytes,
                    "projected_bytes": index_bytes + index_increment,
                },
                "checkpoints": {
                    "current_bytes": checkpoint_bytes,
                    "projected_bytes": checkpoint_bytes + checkpoint_increment,
                },
            },
        }

    async def create_run(self, resume_run_id=None):
        run_id = resume_run_id or str(uuid.uuid4())
        self.run_id = run_id
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stock_bounce_v2_backfill_runs(run_id, status)
                VALUES($1, 'running')
                ON CONFLICT(run_id) DO UPDATE SET status = 'running', updated_at = NOW()
                """,
                run_id,
            )
        return run_id

    async def completed_ranges(self, run_id):
        async with self.pool.acquire() as conn:
            records = await conn.fetch(
                """
                SELECT ticker, start_date, end_date
                FROM stock_bounce_v2_backfill_ranges
                WHERE run_id = $1 AND status = 'complete' AND payload IS NOT NULL
                """,
                run_id,
            )
        return {
            (
                record["ticker"],
                record["start_date"].isoformat() if record["start_date"] else None,
                record["end_date"].isoformat(),
            )
            for record in records
        }

    async def get_range(self, ticker, start_date, end_date):
        async with self.pool.acquire() as conn:
            payload = await conn.fetchval(
                """
                SELECT payload FROM stock_bounce_v2_backfill_ranges
                WHERE run_id = $1 AND ticker = $2
                  AND (($3::date IS NULL AND start_date IS NULL) OR start_date = $3)
                  AND end_date = $4 AND status = 'complete'
                """,
                self.run_id,
                ticker,
                date.fromisoformat(start_date) if start_date else None,
                date.fromisoformat(end_date),
            )
        if payload is None:
            raise RuntimeError(f"v2 checkpoint is missing for {ticker}")
        if isinstance(payload, str):
            payload = json.loads(payload)
        return {**payload, "bounded_bars": []}

    async def record_range(self, run_id, ticker, start_date, end_date, payload):
        checkpoint = {"bars": payload["bars"], "splits": payload["splits"]}
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                bounded = payload["bounded_bars"]
                if bounded:
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
                            for bar in bounded
                        ],
                    )
                if payload["splits"]:
                    await conn.executemany(
                        """
                        INSERT INTO stock_bounce_v2_splits(market, ticker, split_date, ratio)
                        VALUES('US', $1, $2, $3)
                        ON CONFLICT(market, ticker, split_date) DO UPDATE SET
                            ratio = EXCLUDED.ratio
                        """,
                        [
                            (
                                ticker,
                                date.fromisoformat(split["date"]),
                                split["ratio"],
                            )
                            for split in payload["splits"]
                        ],
                    )
                await conn.execute(
                    """
                    INSERT INTO stock_bounce_v2_backfill_ranges(
                        run_id, ticker, start_date, end_date, status, payload
                    ) VALUES($1, $2, $3, $4, 'complete', $5::jsonb)
                    ON CONFLICT(run_id, ticker, end_date) DO UPDATE SET
                        status = 'complete', payload = EXCLUDED.payload, fetched_at = NOW()
                    """,
                    run_id,
                    ticker,
                    date.fromisoformat(start_date) if start_date else None,
                    date.fromisoformat(end_date),
                    json.dumps(checkpoint),
                )

    async def publish_snapshot(self, run_id, date_string, snapshot, watermarks):
        session_date = date.fromisoformat(date_string)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO published_dates(session_date, market) VALUES($1, 'US')
                    ON CONFLICT(session_date, market) DO NOTHING
                    """,
                    session_date,
                )
                await conn.execute(
                    """
                    INSERT INTO published_artifacts(session_date, market, artifact_key, payload)
                    VALUES($1, 'US', 'stock_bounce:v2', $2::jsonb)
                    ON CONFLICT(session_date, market, artifact_key) DO UPDATE SET
                        payload = EXCLUDED.payload, updated_at = NOW()
                    """,
                    session_date,
                    json.dumps(snapshot),
                )
                if watermarks:
                    await conn.executemany(
                        """
                        INSERT INTO stock_bounce_v2_high_watermarks(
                            market, ticker, as_of_date, high
                        ) VALUES('US', $1, $2, $3)
                        ON CONFLICT(market, ticker) DO UPDATE SET
                            as_of_date = EXCLUDED.as_of_date, high = EXCLUDED.high,
                            updated_at = NOW()
                        WHERE stock_bounce_v2_high_watermarks.as_of_date <= EXCLUDED.as_of_date
                        """,
                        [
                            (ticker, date.fromisoformat(value["date"]), value["high"])
                            for ticker, value in watermarks.items()
                        ],
                    )
                membership_rows = [
                    (row["ticker"], universe, session_date, session_date)
                    for row in snapshot["rows"]
                    for universe in row["universes"]
                ]
                if membership_rows:
                    await conn.executemany(
                        """
                        INSERT INTO stock_bounce_v2_memberships(
                            market, ticker, universe, first_seen_date, last_seen_date
                        ) VALUES('US', $1, $2, $3, $4)
                        ON CONFLICT(market, ticker, universe) DO UPDATE SET
                            first_seen_date = LEAST(
                                stock_bounce_v2_memberships.first_seen_date,
                                EXCLUDED.first_seen_date
                            ),
                            last_seen_date = GREATEST(
                                stock_bounce_v2_memberships.last_seen_date,
                                EXCLUDED.last_seen_date
                            )
                        """,
                        membership_rows,
                    )
                await conn.execute(
                    """
                    INSERT INTO stock_bounce_v2_backfill_targets(run_id, session_date, status)
                    VALUES($1, $2, 'complete')
                    ON CONFLICT(run_id, session_date) DO UPDATE SET
                        status = 'complete', error = NULL, updated_at = NOW()
                    """,
                    run_id,
                    session_date,
                )

    async def target_complete(self, run_id, date_string):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM stock_bounce_v2_backfill_targets
                WHERE run_id = $1 AND session_date = $2 AND status = 'complete'
                """,
                run_id,
                date.fromisoformat(date_string),
            )
        return row is not None

    async def cleanup_ranges(self, run_id):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM stock_bounce_v2_backfill_ranges WHERE run_id = $1", run_id
            )

    async def finish_run(self, run_id, report):
        status = "complete" if not report["unpublished"] else "incomplete"
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE stock_bounce_v2_backfill_runs
                SET status = $2, report = $3::jsonb, updated_at = NOW()
                WHERE run_id = $1
                """,
                run_id,
                status,
                json.dumps(report),
            )
