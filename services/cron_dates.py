"""Cron ingest date resolution and session probing."""

from typing import List

from core.markets import MARKETS, normalize_market
from db.mongodb import AsyncIOMotorClient
from db.crud.analytics import get_missing_tickers
from utils.handle_datetimes import get_today_utc_date_in_timezone
from utils.handle_external_apis import get_market_data_provider


async def resolve_ingest_dates_for_market(
    conn: AsyncIOMotorClient, market: str
) -> List[str]:
    """
    Return session dates to ingest: always LastCompletedSession; include
    PriorCompletedSession only when that date still has missing tickers.
    """
    market = normalize_market(market)
    tz = MARKETS[market]["timezone"]
    calendar_end = get_today_utc_date_in_timezone(tz)
    provider = get_market_data_provider(market)

    last_session, prior_session = provider.resolve_session_dates(calendar_end)
    if not last_session:
        raise ValueError(
            f"services/cron_dates: could not resolve LastCompletedSession for {market}"
        )

    dates = [last_session]
    if prior_session:
        missing_prior = await get_missing_tickers(conn, prior_session, market=market)
        if missing_prior:
            dates.append(prior_session)

    return dates
