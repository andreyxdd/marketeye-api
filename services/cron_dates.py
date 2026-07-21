"""Cron ingest date resolution and session probing."""

from typing import List

from core.markets import MARKETS, normalize_market
from db.crud.published_archive import is_session_published
from utils.handle_datetimes import get_today_utc_date_in_timezone
from providers import get_market_data_provider


async def get_missing_tickers(conn, date: str, market: str = "US"):
    """Lazy legacy import; session probe does not need Mongo dependencies."""
    from db.crud.analytics import get_missing_tickers as get_missing

    return await get_missing(conn, date, market=market)


async def unpublished_session_dates(pool, market: str) -> List[str]:
    """Return latest completed sessions that still need publishing."""
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
        dates.append(prior_session)
    return [
        date
        for date in dates
        if not await is_session_published(pool, date, market)
    ]


async def needs_ingest(pool, market: str) -> bool:
    """Return whether a latest completed session is not fully published."""
    return bool(await unpublished_session_dates(pool, market))


async def resolve_ingest_dates_for_market(
    conn, market: str
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
