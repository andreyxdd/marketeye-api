"""Publish Mongo hot-path snapshots into PostgreSQL read-model archive."""

from typing import Optional

import asyncpg

import services.analytics_service as analytics_service
from core.markets import DEFAULT_MARKET, normalize_market
from db.crud.published_archive import (
    MARKET_ARTIFACT_KEY,
    build_criterion_artifact_key,
    build_lists_artifact_key,
    upsert_artifact,
    upsert_ticker_payload,
)
from db.crud.tracking import CRITERIA
from utils.price_bands import PRICE_BANDS


PRICE_BANDS_TO_PUBLISH: list[Optional[str]] = [None, *PRICE_BANDS.keys()]


def _criterion_payload_key(criterion: str) -> str:
    return f"by_{criterion}"


def _collect_tickers(rows: list[dict], bucket: set[str]):
    for row in rows:
        ticker = row.get("ticker")
        if ticker:
            bucket.add(ticker)


async def publish_day(
    conn,
    pool: asyncpg.Pool,
    date: str,
    market: str = DEFAULT_MARKET,
) -> dict:
    """Materialize read-model artifacts for single market/date into PostgreSQL."""
    if pool is None:
        raise RuntimeError("PostgreSQL pool is not initialized")

    market = normalize_market(market)
    tickers_to_publish: set[str] = set()
    artifacts_written = 0

    for price_band in PRICE_BANDS_TO_PUBLISH:
        by_criteria_payload = await analytics_service.get_analytics_lists_by_criteria_hot(
            conn, date, market=market, price_band=price_band
        )
        await upsert_artifact(
            pool,
            date,
            build_lists_artifact_key(price_band),
            by_criteria_payload,
            market=market,
        )
        artifacts_written += 1

        for criterion in CRITERIA:
            rows = by_criteria_payload[_criterion_payload_key(criterion)]
            _collect_tickers(rows, tickers_to_publish)
            await upsert_artifact(
                pool,
                date,
                build_criterion_artifact_key(criterion, price_band),
                {criterion: rows},
                market=market,
            )
            artifacts_written += 1

    if market == "US":
        market_payload = await analytics_service.get_market_analytics_hot(conn, date)
        await upsert_artifact(
            pool,
            date,
            MARKET_ARTIFACT_KEY,
            market_payload,
            market=market,
        )
        artifacts_written += 1

    for ticker in sorted(tickers_to_publish):
        ticker_payload = await analytics_service.get_ticker_analytics_response_hot(
            conn, date, ticker, market=market
        )
        await upsert_ticker_payload(pool, date, ticker, ticker_payload, market=market)

    return {
        "market": market,
        "date": date,
        "artifacts_written": artifacts_written,
        "tickers_written": len(tickers_to_publish),
    }
