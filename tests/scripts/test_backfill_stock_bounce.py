"""Deep StockBounce backfill behavior with strict local and mocked remote bars."""

from datetime import date, timedelta

import pytest

from services.stock_bounce.backfill import (
    LocalBarsResult,
    StockBounceBackfill,
)


class MemoryStore:
    def __init__(self, targets):
        self.targets = targets
        self.snapshots = {}
        self.ranges = {}
        self.runs = {}
        self.next_run = 0

    async def create_run(self, resume_run_id=None):
        if resume_run_id is not None:
            return resume_run_id
        self.next_run += 1
        run_id = f"run-{self.next_run}"
        self.runs[run_id] = {"status": "running"}
        return run_id

    async def list_targets(self, force=False):
        del force
        return [
            {
                **target,
                "snapshot_complete": target["date"] in self.snapshots,
            }
            for target in self.targets
        ]

    async def completed_ranges(self, run_id):
        del run_id
        return set(self.ranges)

    async def get_range(self, ticker, start_date, end_date):
        return self.ranges[(ticker, start_date, end_date)]

    async def record_range(self, run_id, ticker, start_date, end_date, bars):
        del run_id
        self.ranges[(ticker, start_date, end_date)] = bars

    async def publish_snapshot(self, run_id, date_string, snapshot):
        del run_id
        self.snapshots[date_string] = snapshot

    async def target_complete(self, run_id, date_string):
        del run_id
        return date_string in self.snapshots

    async def finish_run(self, run_id, report):
        self.runs[run_id] = report


class LocalAdapter:
    def __init__(self, bars_by_ticker):
        self.bars_by_ticker = bars_by_ticker

    async def fetch(self, ticker, start_date, end_date):
        bars = [
            bar
            for bar in self.bars_by_ticker.get(ticker, [])
            if start_date <= bar["date"] <= end_date
        ]
        return LocalBarsResult(status="complete", bars=bars)


class RemoteAdapter:
    def __init__(self, bars_by_ticker, universe):
        self.bars_by_ticker = bars_by_ticker
        self.universe = universe
        self.calls = []

    async def current_universe(self):
        return self.universe

    async def fetch_range(self, ticker, start_date, end_date):
        self.calls.append((ticker, start_date, end_date))
        return [
            bar
            for bar in self.bars_by_ticker.get(ticker, [])
            if start_date <= bar["date"] <= end_date
        ]


def make_bars(ticker, count=21):
    start = date(2024, 1, 1)
    return [
        {
            "ticker": ticker,
            "date": (start + timedelta(days=index)).isoformat(),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 101.0 if index % 2 else 99.0,
            "volume": 1000,
        }
        for index in range(count)
    ]


def make_targets(*dates):
    return [
        {"date": date_string, "tickers": ["ABC"], "snapshot_complete": False}
        for date_string in dates
    ]


@pytest.mark.asyncio
async def test_complete_local_history_publishes_exact_snapshots_without_remote():
    bars = make_bars("ABC")
    store = MemoryStore(make_targets("2024-01-19", "2024-01-20"))
    remote = RemoteAdapter({}, [])
    runner = StockBounceBackfill(store, LocalAdapter({"ABC": bars}), remote)

    report = await runner.run()

    assert report["unpublished"] == []
    assert report["published"] == ["2024-01-19", "2024-01-20"]
    assert remote.calls == []
    assert store.snapshots["2024-01-19"]["coverage"]["status"] == "exact"


@pytest.mark.asyncio
async def test_remote_ranges_are_coalesced_and_resume_does_not_refetch():
    bars = make_bars("ABC") + make_bars("XYZ")
    targets = make_targets("2024-01-20", "2024-01-21")
    store = MemoryStore(targets)
    local = LocalAdapter({"ABC": bars[-1:], "XYZ": []})
    remote = RemoteAdapter(
        {"ABC": make_bars("ABC"), "XYZ": make_bars("XYZ")}, ["ABC", "XYZ"]
    )
    runner = StockBounceBackfill(store, local, remote, retry_attempts=1)

    first = await runner.run()

    assert first["unpublished"] == []
    assert len(remote.calls) == 2
    assert all(call[0] in ("ABC", "XYZ") for call in remote.calls)
    assert len({call[1] for call in remote.calls}) == 1
    assert all(call[2] == "2024-01-21" for call in remote.calls)
    assert store.snapshots["2024-01-20"]["coverage"]["status"] == "degraded"
    assert store.snapshots["2024-01-20"]["coverage"]["declared_universe_count"] == 2

    del store.snapshots["2024-01-21"]
    calls_before_resume = list(remote.calls)
    resumed = await runner.run(resume_run_id=first["run_id"])

    assert resumed["unpublished"] == []
    assert remote.calls == calls_before_resume


@pytest.mark.asyncio
async def test_insufficient_history_is_an_explicit_exclusion_not_a_partial_vector():
    targets = make_targets("2024-01-20")
    store = MemoryStore(targets)
    short_history = make_bars("ABC", count=20)[-5:]
    remote = RemoteAdapter({"ABC": short_history}, ["ABC"])
    runner = StockBounceBackfill(store, LocalAdapter({}), remote, retry_attempts=1)

    report = await runner.run()

    assert report["unpublished"] == ["2024-01-20"]
    assert "insufficient" in report["errors"]["2024-01-20"]
    assert store.snapshots == {}


@pytest.mark.asyncio
async def test_dry_run_plans_without_remote_or_snapshot_writes():
    store = MemoryStore(make_targets("2024-01-20"))
    remote = RemoteAdapter({"ABC": make_bars("ABC")}, ["ABC"])
    runner = StockBounceBackfill(store, LocalAdapter({}), remote)

    report = await runner.run(dry_run=True)

    assert report["dry_run"] is True
    assert report["targets"] == ["2024-01-20"]
    assert remote.calls == []
    assert store.snapshots == {}


@pytest.mark.asyncio
async def test_storage_failure_is_not_misread_as_absent_history():
    class StorageFailure:
        async def fetch(self, ticker, start_date, end_date):
            del ticker, start_date, end_date
            return LocalBarsResult(
                status="storage_error", bars=[], error="connection failed"
            )

    store = MemoryStore(make_targets("2024-01-20"))
    remote = RemoteAdapter({"ABC": make_bars("ABC")}, ["ABC"])
    runner = StockBounceBackfill(store, StorageFailure(), remote)

    report = await runner.run()

    assert "local bars unavailable" in report["errors"]["2024-01-20"]
    assert remote.calls == []
    assert store.snapshots == {}


@pytest.mark.asyncio
async def test_remote_range_retries_then_checkpoints_success():
    class FlakyRemote(RemoteAdapter):
        async def fetch_range(self, ticker, start_date, end_date):
            if not self.calls:
                self.calls.append((ticker, start_date, end_date))
                raise RuntimeError("temporary failure")
            return await super().fetch_range(ticker, start_date, end_date)

    store = MemoryStore(make_targets("2024-01-20"))
    remote = FlakyRemote({"ABC": make_bars("ABC")}, ["ABC"])
    runner = StockBounceBackfill(store, LocalAdapter({}), remote, retry_attempts=2)

    report = await runner.run()

    assert report["unpublished"] == []
    assert len(remote.calls) == 2
    assert len(store.ranges) == 1
