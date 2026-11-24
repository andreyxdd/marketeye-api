"""Cron ingest date resolution, session probing, and freshness reporting."""

import asyncio
import logging
import multiprocessing
from datetime import datetime, timezone
from time import monotonic
from typing import List

from core.markets import MARKETS, normalize_market
from db.crud.published_archive import (
    STOCK_BOUNCE_ARTIFACT_KEY,
    STOCK_BOUNCE_V2_ARTIFACT_KEY,
    get_artifact_payload,
    get_latest_artifact_date,
    get_latest_published_date,
    is_archive_complete,
)
from utils.handle_datetimes import get_today_utc_date_in_timezone
from providers import get_market_data_provider


logger = logging.getLogger(__name__)

_PROVIDER_PROBE_TIMEOUT_SECONDS = 10.0
_PROVIDER_PROCESS_METHOD = "spawn"
_PROVIDER_PROCESS_POLL_SECONDS = 0.02
_PROVIDER_PROCESS_CLEANUP_SECONDS = 0.2


class _ProviderProbeError(RuntimeError):
    """Safe provider failure metadata returned across the process boundary."""

    def __init__(self, error_type: str):
        super().__init__("provider probe failed")
        self.error_type = error_type


def _provider_probe_worker(market, calendar_end, timeout_seconds, sender):
    try:
        provider = get_market_data_provider(market)
        sessions = provider.resolve_session_dates(
            calendar_end, timeout_seconds=timeout_seconds
        )
    except Exception as error:  # pylint: disable=broad-except
        result = ("error", type(error).__name__)
    else:
        result = ("ok", sessions)
    try:
        sender.send(result)
    except (BrokenPipeError, EOFError):
        pass
    finally:
        sender.close()


def _cleanup_provider_process(process):
    if process.is_alive():
        process.terminate()
        process.join(timeout=_PROVIDER_PROCESS_CLEANUP_SECONDS)
    if process.is_alive():
        process.kill()
        process.join(timeout=_PROVIDER_PROCESS_CLEANUP_SECONDS)
    process.join(timeout=0)
    if not process.is_alive():
        process.close()


async def _resolve_freshness_sessions(market, calendar_end, timeout_seconds):
    context = multiprocessing.get_context(_PROVIDER_PROCESS_METHOD)
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_provider_probe_worker,
        args=(market, calendar_end, timeout_seconds, sender),
    )
    deadline = monotonic() + timeout_seconds
    try:
        process.start()
    except Exception:
        receiver.close()
        sender.close()
        process.close()
        raise
    sender.close()
    try:
        while True:
            if receiver.poll(0):
                status, payload = receiver.recv()
                if status == "error":
                    raise _ProviderProbeError(payload)
                return payload
            if process.exitcode is not None:
                raise _ProviderProbeError("ProcessExit")
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("freshness provider deadline exceeded")
            await asyncio.sleep(min(_PROVIDER_PROCESS_POLL_SECONDS, remaining))
    finally:
        _cleanup_provider_process(process)
        receiver.close()


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
    last_session, prior_session = await asyncio.to_thread(
        provider.resolve_session_dates, calendar_end
    )
    if not last_session:
        raise ValueError(
            f"services/cron_dates: could not resolve LastCompletedSession for {market}"
        )

    dates = [last_session]
    if prior_session:
        dates.append(prior_session)
    unpublished = [
        date for date in dates if not await is_archive_complete(pool, date, market)
    ]
    if market == "US":
        unpublished.sort()
    return unpublished


async def needs_ingest(pool, market: str) -> bool:
    """Return whether a latest completed session is not fully published."""
    return bool(await unpublished_session_dates(pool, market))


async def resolve_ingest_dates_for_market(conn, market: str) -> List[str]:
    """
    Return session dates to ingest: always LastCompletedSession; include
    PriorCompletedSession only when that date still has missing tickers.
    """
    market = normalize_market(market)
    tz = MARKETS[market]["timezone"]
    calendar_end = get_today_utc_date_in_timezone(tz)
    provider = get_market_data_provider(market)

    last_session, prior_session = await asyncio.to_thread(
        provider.resolve_session_dates, calendar_end
    )
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


def _checked_at_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


async def freshness_report(pool) -> dict:
    """Return public operational freshness for the latest provider sessions."""
    markets = {}
    for market, config in MARKETS.items():
        component_names = ["analytics"]
        if market == "US":
            component_names.extend(("stock_bounce_v1", "stock_bounce_v2"))
        try:
            calendar_end = get_today_utc_date_in_timezone(config["timezone"])
            expected_session, _ = await _resolve_freshness_sessions(
                market, calendar_end, _PROVIDER_PROBE_TIMEOUT_SECONDS
            )
            if not expected_session:
                raise ValueError(f"could not resolve LastCompletedSession for {market}")
        except Exception as error:  # pylint: disable=broad-except
            error_type = (
                error.error_type
                if isinstance(error, _ProviderProbeError)
                else type(error).__name__
            )
            logger.error(
                "Freshness provider probe failed for %s (%s)", market, error_type
            )
            markets[market] = {
                "expected_session": None,
                "components": {
                    name: {"status": "unavailable", "latest_session": None}
                    for name in component_names
                },
            }
            continue

        try:
            analytics_fresh = await is_archive_complete(pool, expected_session, market)
            latest_session = await get_latest_published_date(pool, market)
            analytics = {
                "status": "fresh" if analytics_fresh else "stale",
                "latest_session": latest_session,
            }
        except Exception as error:  # pylint: disable=broad-except
            logger.error(
                "Freshness analytics lookup failed for %s (%s)",
                market,
                type(error).__name__,
            )
            analytics = {"status": "unavailable", "latest_session": None}
        components = {"analytics": analytics}

        if market == "US":
            from services.stock_bounce.semantics import validate_snapshot
            from services.stock_bounce.semantics_v2 import validate_snapshot_v2

            artifact_types = (
                (
                    "stock_bounce_v1",
                    STOCK_BOUNCE_ARTIFACT_KEY,
                    validate_snapshot,
                ),
                (
                    "stock_bounce_v2",
                    STOCK_BOUNCE_V2_ARTIFACT_KEY,
                    validate_snapshot_v2,
                ),
            )
            for component_name, artifact_key, validator in artifact_types:
                try:
                    snapshot = await get_artifact_payload(
                        pool, expected_session, artifact_key, market=market
                    )
                    latest_artifact = await get_latest_artifact_date(
                        pool, artifact_key, market=market
                    )
                except Exception as error:  # pylint: disable=broad-except
                    logger.error(
                        "Freshness artifact lookup failed for %s %s (%s)",
                        market,
                        component_name,
                        type(error).__name__,
                    )
                    components[component_name] = {
                        "status": "unavailable",
                        "latest_session": None,
                    }
                    continue

                artifact_fresh = snapshot is not None
                if snapshot is not None:
                    try:
                        validator(snapshot)
                    except (KeyError, OverflowError, TypeError, ValueError):
                        artifact_fresh = False
                    else:
                        artifact_fresh = snapshot["date"] == expected_session
                components[component_name] = {
                    "status": "fresh" if artifact_fresh else "stale",
                    "latest_session": latest_artifact,
                }

        markets[market] = {
            "expected_session": expected_session,
            "components": components,
        }

    component_statuses = [
        component["status"]
        for market in markets.values()
        for component in market["components"].values()
    ]
    if any(status == "unavailable" for status in component_statuses):
        overall_status = "unavailable"
    elif all(status == "fresh" for status in component_statuses):
        overall_status = "fresh"
    else:
        overall_status = "stale"
    return {
        "status": overall_status,
        "checked_at": _checked_at_utc(),
        "markets": markets,
    }
