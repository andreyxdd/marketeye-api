"""Analytics orchestration — routes and cron delegate here."""

import asyncio
from typing import Optional

from db.mongodb import AsyncIOMotorClient
from db.crud.analytics import (
    get_analytics_sorted_by as crud_get_analytics_sorted_by,
    get_dates as crud_get_dates,
    get_missing_tickers,
    get_normalazied_cvi_slope,
    insert_analytics_batch,
)
from db.crud.scrapes import get_mentions
from db.crud.tracking import get_analytics_frequencies
from core.markets import DEFAULT_MARKET, normalize_market
from utils.handle_datetimes import get_last_quater_date, get_date_string
from utils.handle_external_apis import (
    get_market_sp500,
    get_market_vixs,
    get_quarterly_free_cash_flow_polygon,
    get_ticker_analytics as external_get_ticker_analytics,
    get_ticker_extra_analytics as external_get_ticker_extra_analytics,
    get_ticker_base_analytics as external_get_ticker_base_analytics,
    get_tickers as external_get_tickers,
)


def _to_stub_mentions() -> dict:
    return {
        "mentions_over_one_day": 0,
        "mentions_over_two_days": 0,
        "mentions_over_three_days": 0,
    }


async def enrich_ticker_row(
    conn: AsyncIOMotorClient,
    base_row: dict,
    criterion: str,
    market: str = DEFAULT_MARKET,
) -> dict:
    market = normalize_market(market)
    ticker = base_row["ticker"]
    date = get_date_string(base_row["date"])

    if market == "US":
        return {
            **base_row,
            **external_get_ticker_extra_analytics(ticker, date, market=market),
            **await get_mentions(conn, ticker, date),
            "fcf": get_quarterly_free_cash_flow_polygon(ticker, get_last_quater_date(date)),
            "frequencies": await get_analytics_frequencies(
                conn, date, criterion, ticker, market=market
            ),
        }

    return {
        **base_row,
        **external_get_ticker_extra_analytics(ticker, date, market=market),
        **_to_stub_mentions(),
        "fcf": "",
        "frequencies": await get_analytics_frequencies(
            conn, date, criterion, ticker, market=market
        ),
    }


async def get_ticker_analytics_response(
    conn: AsyncIOMotorClient,
    date: str,
    ticker: str,
    market: str = DEFAULT_MARKET,
    criterion: Optional[str] = None,
) -> dict:
    market = normalize_market(market)
    last_quater_limit_date = get_last_quater_date(date)

    if market == "US":
        return {
            **external_get_ticker_analytics(ticker, date, 45, 15, market=market),
            **await get_mentions(conn, ticker, date),
            "fcf": get_quarterly_free_cash_flow_polygon(ticker, last_quater_limit_date),
            "frequencies": await get_analytics_frequencies(
                conn, date, criterion, ticker, market=market
            ),
        }

    return {
        **external_get_ticker_analytics(ticker, date, 45, 15, market=market),
        **_to_stub_mentions(),
        "fcf": "",
        "frequencies": await get_analytics_frequencies(
            conn, date, criterion, ticker, market=market
        ),
    }


async def get_market_analytics(db: AsyncIOMotorClient, date: str) -> dict:
    return {
        "SP500": get_market_sp500(date),
        **get_market_vixs(date),
        "normalazied_CVI_slope": float(await get_normalazied_cvi_slope(db, date)),
    }


async def get_analytics_sorted_by(
    conn: AsyncIOMotorClient,
    date: str,
    criterion: str,
    market: str = DEFAULT_MARKET,
    lim: Optional[int] = 20,
) -> list:
    return await crud_get_analytics_sorted_by(
        conn, date, criterion, lim, market=market, enrich_fn=enrich_ticker_row
    )


async def get_analytics_lists_by_criteria(
    conn: AsyncIOMotorClient, date: str, market: str = DEFAULT_MARKET
) -> dict:
    market = normalize_market(market)
    futures = [
        get_analytics_sorted_by(conn, date, "one_day_avg_mf", market=market),
        get_analytics_sorted_by(conn, date, "three_day_avg_mf", market=market),
        get_analytics_sorted_by(conn, date, "volume", market=market),
        get_analytics_sorted_by(conn, date, "three_day_avg_volume", market=market),
        get_analytics_sorted_by(conn, date, "macd", market=market),
    ]
    res = await asyncio.gather(*futures)
    return {
        "by_one_day_avg_mf": res[0],
        "by_three_day_avg_mf": res[1],
        "by_volume": res[2],
        "by_three_day_avg_volume": res[3],
        "by_macd": res[4],
    }


async def get_dates(conn: AsyncIOMotorClient, market: str = DEFAULT_MARKET) -> list:
    return await crud_get_dates(conn, market=market)


async def get_frequencies_for_tickers(
    conn: AsyncIOMotorClient,
    date: str,
    criterion: str,
    tickers: list[str],
    market: str = DEFAULT_MARKET,
) -> list:
    market = normalize_market(market)
    frequencies = []
    for ticker in tickers:
        frequencies.append(
            await get_analytics_frequencies(conn, date, criterion, ticker, market=market)
        )
    return frequencies


def get_free_cash_flow(ticker: str, date: str, market: str = DEFAULT_MARKET):
    market = normalize_market(market)
    if market != "US":
        return ""
    last_quater_limit_date = get_last_quater_date(date)
    return get_quarterly_free_cash_flow_polygon(ticker, last_quater_limit_date)


async def ingest_base_analytics_for_market(
    conn: AsyncIOMotorClient, date: str, market: str = DEFAULT_MARKET
) -> str:
    from core.settings import CRON_INSERT_BATCH_SIZE, CRON_MAX_WORKERS
    from utils.handle_datetimes import get_date_string, get_epoch

    market = normalize_market(market)
    tickers_to_insert = await get_missing_tickers(conn, date, market=market)
    n_tickers = len(tickers_to_insert)
    msg = []

    if not tickers_to_insert:
        msg.append(
            f"services/analytics_service ingest_base_analytics_for_market:"
            f" No tickers to insert for {market} on {date}"
        )
        return "\n\n".join(msg)

    msg.append(
        f"services/analytics_service ingest_base_analytics_for_market:"
        f" {n_tickers} tickers to analyze for {market} on {date}"
        f" (epoch {get_epoch(date)})"
    )

    sem = asyncio.Semaphore(CRON_MAX_WORKERS)

    async def process_ticker(ticker: str):
        async with sem:
            return await asyncio.to_thread(
                external_get_ticker_base_analytics,
                ticker,
                date,
                market=market,
            )

    results = await asyncio.gather(*[process_ticker(t) for t in tickers_to_insert])

    analytics_to_insert = []
    for ticker, ticker_base_analytics in zip(tickers_to_insert, results):
        if not ticker_base_analytics:
            continue
        date_str = get_date_string(ticker_base_analytics["date"])
        if date_str != date:
            msg.append(
                f"services/analytics_service: skipped {ticker} — "
                f"date mismatch {date_str} vs {date}"
            )
            continue
        ticker_base_analytics["market"] = market
        analytics_to_insert.append(ticker_base_analytics)

    msg.append(
        f"services/analytics_service: computed {len(analytics_to_insert)} rows for {market}"
    )

    if analytics_to_insert:
        inserted = await insert_analytics_batch(
            conn, analytics_to_insert, batch_size=CRON_INSERT_BATCH_SIZE
        )
        msg.append(f"services/analytics_service: inserted {inserted} documents")

    return "\n\n".join(msg)
