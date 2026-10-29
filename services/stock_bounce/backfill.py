"""Resumable, range-coalesced StockBounce historical reconstruction."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from core.settings import EODHD_API_KEY

from .semantics import build_snapshot, build_stock_bounce_analytics


def sanitize_provider_text(value) -> str:
    text = str(value)
    if EODHD_API_KEY:
        text = text.replace(EODHD_API_KEY, "REDACTED")
    return re.sub(
        r"((?:api_token|api_key)=)[^&\s]+",
        r"\1REDACTED",
        text,
        flags=re.IGNORECASE,
    )


@dataclass(frozen=True)
class LocalBarsResult:
    status: str
    bars: list[dict]
    error: Optional[str] = None


def _complete_history(bars: list[dict], target_date: str) -> bool:
    eligible = [bar for bar in bars if bar["date"] <= target_date]
    return len(eligible) >= 19 and eligible[-1]["date"] == target_date


def _history_exclusion(ticker: str, bars: list[dict], target_date: str) -> dict:
    eligible = [bar for bar in bars if bar["date"] <= target_date]
    if not eligible or eligible[-1]["date"] != target_date:
        reason = "target_session_bar_absent"
    else:
        reason = "insufficient_preceding_trading_bars"
    return {"ticker": ticker, "reason": reason, "available_bars": len(eligible)}


class StockBounceBackfill:
    def __init__(self, store, local_bars, remote_bars, retry_attempts: int = 3):
        self.store = store
        self.local_bars = local_bars
        self.remote_bars = remote_bars
        self.retry_attempts = retry_attempts

    async def _fetch_range_with_retry(self, ticker: str, start: str, end: str):
        last_error = None
        for attempt in range(self.retry_attempts):
            try:
                return await self.remote_bars.fetch_range(ticker, start, end)
            except Exception as error:  # pylint: disable=broad-except
                last_error = sanitize_provider_text(error)
                if attempt + 1 < self.retry_attempts:
                    await asyncio.sleep(0.1 * (2**attempt))
        raise RuntimeError(f"EODHD range failed for {ticker} {start}..{end}: {last_error}")

    async def run(
        self,
        *,
        resume_run_id=None,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict:
        targets = await self.store.list_targets()
        targets = [
            target
            for target in targets
            if force or resume_run_id or not target["snapshot_complete"]
        ]
        target_dates = [target["date"] for target in targets]
        if dry_run:
            return {
                "run_id": resume_run_id,
                "dry_run": True,
                "targets": target_dates,
                "ticker_count": len(
                    {ticker for target in targets for ticker in target["tickers"]}
                ),
            }

        run_id = await self.store.create_run(resume_run_id=resume_run_id)
        report = {
            "run_id": run_id,
            "dry_run": False,
            "targets": target_dates,
            "published": [],
            "unpublished": [],
            "errors": {},
        }
        if not targets:
            await self.store.finish_run(run_id, report)
            return report

        start_date = (
            min(date.fromisoformat(value) for value in target_dates)
            - timedelta(days=120)
        ).isoformat()
        end_date = max(target_dates)
        local_cache = {}
        target_universes = {}
        target_uses_remote = set()

        for target in targets:
            target_date = target["date"]
            archived = list(target["tickers"])
            remote_needed = False
            for ticker in archived:
                key = (ticker, target_date)
                result = await self.local_bars.fetch(ticker, start_date, target_date)
                local_cache[key] = list(result.bars)
                if result.status == "storage_error":
                    report["errors"][target_date] = (
                        f"local bars unavailable for {ticker}: {result.error}"
                    )
                    break
                if not _complete_history(result.bars, target_date):
                    remote_needed = True
            if target_date in report["errors"]:
                continue
            if remote_needed:
                try:
                    current = await self.remote_bars.current_universe()
                except Exception as error:  # pylint: disable=broad-except
                    raise RuntimeError(sanitize_provider_text(error)) from None
                target_universes[target_date] = sorted(set(archived) | set(current))
                target_uses_remote.add(target_date)
            else:
                target_universes[target_date] = sorted(archived)

        completed_ranges = await self.store.completed_ranges(run_id)
        range_cache = {}
        range_errors = {}
        tickers_to_fetch = {
            ticker
            for target_date in target_uses_remote
            for ticker in target_universes[target_date]
        }
        for ticker in sorted(tickers_to_fetch):
            range_key = (ticker, start_date, end_date)
            if range_key in completed_ranges:
                range_cache[ticker] = await self.store.get_range(*range_key)
                continue
            try:
                bars = await self._fetch_range_with_retry(ticker, start_date, end_date)
                normalized = sorted(
                    ({**bar, "ticker": ticker, "date": bar["date"][:10]} for bar in bars),
                    key=lambda bar: bar["date"],
                )
                await self.store.record_range(
                    run_id, ticker, start_date, end_date, normalized
                )
                range_cache[ticker] = normalized
            except Exception as error:  # pylint: disable=broad-except
                range_errors[ticker] = str(error)

        for target in targets:
            target_date = target["date"]
            if target_date in report["errors"]:
                report["unpublished"].append(target_date)
                continue
            if await self.store.target_complete(run_id, target_date):
                report["published"].append(target_date)
                continue
            failed_tickers = sorted(
                set(target_universes.get(target_date, [])) & set(range_errors)
            )
            if failed_tickers:
                report["errors"][target_date] = "; ".join(
                    range_errors[ticker] for ticker in failed_tickers
                )
                report["unpublished"].append(target_date)
                continue

            rows = []
            exclusions = []
            for ticker in target_universes[target_date]:
                bars = range_cache.get(ticker) or local_cache.get((ticker, target_date), [])
                eligible = sorted(
                    (bar for bar in bars if bar["date"] <= target_date),
                    key=lambda bar: bar["date"],
                )
                if not _complete_history(eligible, target_date):
                    exclusions.append(_history_exclusion(ticker, eligible, target_date))
                    continue
                rows.append(build_stock_bounce_analytics(eligible))

            if not rows:
                reason = exclusions[0]["reason"] if exclusions else "empty universe"
                report["errors"][target_date] = f"insufficient usable history: {reason}"
                report["unpublished"].append(target_date)
                continue
            degraded = target_date in target_uses_remote
            snapshot = build_snapshot(
                target_date,
                rows,
                coverage="degraded" if degraded else "exact",
                universe_provenance=(
                    "archived_tickers+current_eodhd_universe"
                    if degraded
                    else "archived_tickers+local_ohlcv"
                ),
                exclusions=exclusions,
            )
            await self.store.publish_snapshot(run_id, target_date, snapshot)
            report["published"].append(target_date)

        await self.store.finish_run(run_id, report)
        return report
