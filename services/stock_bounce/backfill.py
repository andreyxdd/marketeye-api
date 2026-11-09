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
        raise RuntimeError(
            f"EODHD range failed for {ticker} {start}..{end}: {last_error}"
        )

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
                    report["errors"][
                        target_date
                    ] = f"local bars unavailable for {ticker}: {result.error}"
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
                    (
                        {**bar, "ticker": ticker, "date": bar["date"][:10]}
                        for bar in bars
                    ),
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
                bars = range_cache.get(ticker) or local_cache.get(
                    (ticker, target_date), []
                )
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


class StockBounceStorageLimitError(RuntimeError):
    """Raised before writes when the projected database exceeds its safety budget."""

    def __init__(self, current_bytes: int, projected_bytes: int, limit_bytes: int):
        super().__init__(
            "StockBounce v2 backfill refused: projected usage exceeds 70% of "
            "PG_STORAGE_LIMIT_BYTES"
        )
        self.current_bytes = current_bytes
        self.projected_bytes = projected_bytes
        self.limit_bytes = limit_bytes


class StockBounceBackfillV2:
    """Bounded one-year snapshot reconstruction with temporary range checkpoints."""

    def __init__(
        self,
        store,
        local_bars,
        remote_bars,
        retry_attempts: int = 3,
        max_concurrency: int = 4,
        storage_limit_bytes=None,
    ):
        from core.settings import PG_STORAGE_LIMIT_BYTES

        self.store = store
        self.local_bars = local_bars
        self.remote_bars = remote_bars
        self.retry_attempts = retry_attempts
        self.max_concurrency = max(1, int(max_concurrency))
        self.storage_limit_bytes = storage_limit_bytes or PG_STORAGE_LIMIT_BYTES

    async def _fetch_payload(self, ticker: str, end_date: str) -> dict:
        last_error = None
        for attempt in range(self.retry_attempts):
            try:
                bars = await self.remote_bars.fetch_range(ticker, None, end_date)
                splits = await self.remote_bars.fetch_splits(ticker)
                normalized = sorted(
                    (
                        {
                            **bar,
                            "ticker": ticker,
                            "date": bar["date"][:10],
                            "open": float(bar["open"]),
                            "high": float(bar["high"]),
                            "low": float(bar["low"]),
                            "close": float(bar["close"]),
                            "volume": int(bar["volume"]),
                        }
                        for bar in bars
                        if bar["date"][:10] <= end_date
                    ),
                    key=lambda bar: bar["date"],
                )
                from .history import split_ratio

                normalized_splits = [
                    {
                        "date": split.get("date", split.get("split_date"))[:10],
                        "ratio": split_ratio(split),
                    }
                    for split in splits
                    if split.get("date", split.get("split_date"))[:10] <= end_date
                ]
                return {"bars": normalized, "splits": normalized_splits}
            except Exception as error:  # pylint: disable=broad-except
                last_error = sanitize_provider_text(error)
                if attempt + 1 < self.retry_attempts:
                    await asyncio.sleep(0.1 * (2**attempt))
        raise RuntimeError(f"EODHD full history failed for {ticker}: {last_error}")

    async def run(
        self,
        *,
        resume_run_id=None,
        dry_run: bool = False,
        force: bool = False,
        as_of=None,
    ) -> dict:
        from .history import advance_high_watermark, bounded_bars
        from .semantics_v2 import UNIVERSES, build_snapshot_v2

        end = (
            date.fromisoformat(as_of)
            if isinstance(as_of, str)
            else as_of or date.today()
        )
        since = (end - timedelta(days=365)).isoformat()
        all_targets = await self.store.list_targets(since)
        targets = [
            target
            for target in all_targets
            if force or resume_run_id or not target["snapshot_complete"]
        ]
        target_dates = [target["date"] for target in targets]
        base_lookback = min(
            (int(target.get("max_lookback", 0)) for target in all_targets),
            default=0,
        )
        planned_lookbacks = {
            target["date"]: min(1260, base_lookback + index)
            for index, target in enumerate(all_targets)
        }
        tickers = sorted(
            {
                ticker
                for target in targets
                for ticker in set(target["tickers"])
                | set(target.get("macd_tickers", []))
            }
        )
        estimate = await self.store.estimate_storage(targets, self.storage_limit_bytes)
        storage = {
            "current_bytes": int(estimate["current_bytes"]),
            "projected_bytes": int(estimate["projected_bytes"]),
            "limit_bytes": int(self.storage_limit_bytes),
            "components": dict(estimate["components"]),
        }
        if dry_run:
            return {
                "run_id": resume_run_id,
                "dry_run": True,
                "since": since,
                "targets": target_dates,
                "ticker_count": len(tickers),
                **storage,
            }
        if storage["projected_bytes"] > 0.70 * self.storage_limit_bytes:
            raise StockBounceStorageLimitError(
                storage["current_bytes"],
                storage["projected_bytes"],
                self.storage_limit_bytes,
            )

        run_id = await self.store.create_run(resume_run_id=resume_run_id)
        report = {
            "run_id": run_id,
            "dry_run": False,
            "since": since,
            "targets": target_dates,
            "published": [],
            "unpublished": [],
            "errors": {},
            **storage,
            "range_count": len(tickers),
            "checkpoints_removed": False,
        }
        if not targets:
            await self.store.finish_run(run_id, report)
            return report

        pending = []
        for target in targets:
            if resume_run_id and await self.store.target_complete(
                run_id, target["date"]
            ):
                report["published"].append(target["date"])
            else:
                pending.append(target)
        tickers = sorted(
            {
                ticker
                for target in pending
                for ticker in set(target["tickers"])
                | set(target.get("macd_tickers", []))
            }
        )
        end_date = max(target["date"] for target in targets)
        first_date = min(target["date"] for target in targets)
        completed = await self.store.completed_ranges(run_id)
        rows = {target["date"]: [] for target in pending}
        watermarks = {target["date"]: {} for target in pending}
        exclusions = {
            target["date"]: {universe: 0 for universe in UNIVERSES}
            for target in pending
        }
        range_errors = {}

        def memberships(ticker, target):
            return [
                universe
                for universe, declared in (
                    ("whole_market", target["tickers"]),
                    ("macd_history", target.get("macd_tickers", [])),
                )
                if ticker in declared
            ]

        def materialize(ticker, payload):
            target_by_date = {
                target["date"]: target
                for target in pending
                if ticker
                in set(target["tickers"]) | set(target.get("macd_tickers", []))
            }
            watermark = None
            seen_targets = set()
            for bar in payload["bars"]:
                previous, watermark = advance_high_watermark(
                    watermark, bar, payload["splits"]
                )
                target_date = bar["date"]
                if target_date not in target_by_date:
                    continue
                seen_targets.add(target_date)
                target = target_by_date[target_date]
                watermarks[target_date][ticker] = watermark
                if previous is None:
                    for universe in memberships(ticker, target):
                        exclusions[target_date][universe] += 1
                    continue
                rows[target_date].append(
                    {
                        "ticker": ticker,
                        "open": float(bar["open"]),
                        "high": float(bar["high"]),
                        "close": float(bar["close"]),
                        "volume": int(bar["volume"]),
                        "previous_all_time_high": previous,
                        "universes": memberships(ticker, target),
                    }
                )
            for target_date, target in target_by_date.items():
                if target_date not in seen_targets:
                    for universe in memberships(ticker, target):
                        exclusions[target_date][universe] += 1

        queue = asyncio.Queue()
        for ticker in tickers:
            queue.put_nowait(ticker)

        async def worker():
            while True:
                try:
                    ticker = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                range_key = (ticker, None, end_date)
                try:
                    if range_key in completed:
                        payload = await self.store.get_range(ticker, None, end_date)
                    else:
                        payload = await self._fetch_payload(ticker, end_date)
                        payload["bounded_bars"] = bounded_bars(
                            payload["bars"], first_date, end_date
                        )
                        await self.store.record_range(
                            run_id, ticker, None, end_date, payload
                        )
                    materialize(ticker, payload)
                except Exception as error:  # pylint: disable=broad-except
                    range_errors[ticker] = sanitize_provider_text(error)
                finally:
                    queue.task_done()

        if tickers:
            await asyncio.gather(
                *(worker() for _ in range(min(self.max_concurrency, len(tickers))))
            )

        for target in pending:
            target_date = target["date"]
            declared = set(target["tickers"]) | set(target.get("macd_tickers", []))
            failed = sorted(declared & set(range_errors))
            if failed:
                report["errors"][target_date] = "; ".join(
                    f"{ticker}: {range_errors[ticker]}" for ticker in failed
                )
                report["unpublished"].append(target_date)
                continue
            estimated = bool(target.get("estimated", False))
            coverage = {}
            for universe in UNIVERSES:
                base_exclusions = int(target.get(f"{universe}_exclusions", 0))
                count = exclusions[target_date][universe] + base_exclusions
                universe_estimated = bool(
                    target.get(f"{universe}_estimated", estimated)
                )
                coverage[universe] = {
                    "status": "degraded" if universe_estimated or count else "exact",
                    "universe_provenance": target.get(
                        f"{universe}_provenance",
                        (
                            "archived_tickers+local_ohlcv"
                            if universe == "whole_market"
                            else "recoverable_macd_membership"
                        ),
                    ),
                    "exclusions_count": count,
                }
            snapshot = build_snapshot_v2(
                target_date,
                rows[target_date],
                coverage=coverage,
                max_lookback=planned_lookbacks[target_date],
            )
            await self.store.publish_snapshot(
                run_id, target_date, snapshot, watermarks[target_date]
            )
            report["published"].append(target_date)

        if not report["unpublished"]:
            await self.store.cleanup_ranges(run_id)
            report["checkpoints_removed"] = True
        await self.store.finish_run(run_id, report)
        return report
