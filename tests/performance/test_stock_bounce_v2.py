"""Representative PostgreSQL snapshot and set-based v2 read performance gate."""

import json
from datetime import date, timedelta
from statistics import quantiles
from time import perf_counter

import pytest

from db.crud.published_archive import STOCK_BOUNCE_V2_ARTIFACT_KEY, upsert_artifact
from services.stock_bounce.reads import evaluate_session_v2
from services.stock_bounce.semantics_v2 import build_snapshot_v2


@pytest.mark.asyncio
async def test_six_thousand_ticker_five_year_read_p95_below_two_seconds(
    postgres_pool,
):
    first_day = date(2040, 1, 1)
    prior_days = [first_day + timedelta(days=index) for index in range(1260)]
    previous_day = prior_days[-1]
    target_day = first_day + timedelta(days=1260)
    coverage = {
        universe: {
            "status": "exact",
            "universe_provenance": "performance_fixture",
            "exclusions_count": 0,
        }
        for universe in ("whole_market", "macd_history")
    }
    rows = [
        {
            "ticker": f"PERF{index:05d}",
            "open": 100.0,
            "high": 111.0,
            "close": 101.0 + (index % 20) / 10,
            "volume": 1000 + index,
            "previous_all_time_high": 110.0,
            "universes": ["whole_market", "macd_history"],
        }
        for index in range(6000)
    ]
    tickers = [row["ticker"] for row in rows]
    snapshot = build_snapshot_v2(
        target_day.isoformat(), rows, coverage=coverage, max_lookback=1260
    )

    try:
        async with postgres_pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO published_dates(session_date, market) VALUES($1, 'US')
                ON CONFLICT(session_date, market) DO NOTHING
                """,
                [(day,) for day in prior_days],
            )
            await conn.executemany(
                """
                INSERT INTO published_artifacts(
                    session_date, market, artifact_key, payload
                ) VALUES($1, 'US', $2, $3::jsonb)
                ON CONFLICT(session_date, market, artifact_key) DO UPDATE SET
                    payload = EXCLUDED.payload
                """,
                [
                    (
                        day,
                        STOCK_BOUNCE_V2_ARTIFACT_KEY,
                        json.dumps(
                            {
                                "schema_version": 2,
                                "market": "US",
                                "date": day.isoformat(),
                                "max_lookback": 0,
                                "rows": [],
                                "coverage": coverage,
                            }
                        ),
                    )
                    for day in prior_days
                ],
            )
            await conn.executemany(
                """
                INSERT INTO ohlcv_bars(
                    market, ticker, session_date, open, high, low, close, volume
                ) VALUES('US', $1, $2, 100, 100, 90, $3, 1000)
                ON CONFLICT(market, ticker, session_date) DO UPDATE SET
                    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                    close = EXCLUDED.close, volume = EXCLUDED.volume
                """,
                [
                    (ticker, day, close)
                    for ticker in tickers
                    for day, close in ((first_day, 100.0), (previous_day, 90.0))
                ],
            )
        await upsert_artifact(
            postgres_pool,
            target_day.isoformat(),
            STOCK_BOUNCE_V2_ARTIFACT_KEY,
            snapshot,
        )

        durations = []
        for _ in range(9):
            started = perf_counter()
            result = await evaluate_session_v2(
                postgres_pool,
                date_string=target_day.isoformat(),
                lookback=1260,
            )
            durations.append(perf_counter() - started)

        assert len(result["whole_market"]["rows"]) == 20
        assert len(result["macd_history"]["rows"]) == 20
        p95 = quantiles(durations, n=20, method="inclusive")[-1]
        assert p95 < 2.0, f"v2 PostgreSQL read p95={p95:.3f}s"
    finally:
        async with postgres_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM published_dates WHERE session_date = ANY($1::date[])",
                [*prior_days, target_day],
            )
            await conn.execute(
                """
                DELETE FROM ohlcv_bars
                WHERE market = 'US' AND ticker = ANY($1::text[])
                  AND session_date = ANY($2::date[])
                """,
                tickers,
                [first_day, previous_day],
            )
