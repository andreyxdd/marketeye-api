"""One-year, resumable StockBounce v2 backfill and CLI storage gates."""

import asyncio
from datetime import date

import pytest

import scripts.backfill_stock_bounce as cli
from services.stock_bounce.backfill import (
    StockBounceBackfillV2,
    StockBounceStorageLimitError,
)


def _bar(ticker, day, high, close=101.0):
    return {
        "ticker": ticker,
        "date": day,
        "open": 100.0,
        "high": high,
        "low": 90.0,
        "close": close,
        "volume": 1000,
    }


class MemoryStoreV2:
    def __init__(self, targets, *, current=100, projected=200):
        self.targets = targets
        self.current = current
        self.projected = projected
        self.snapshots = {}
        self.ranges = {}
        self.runs = {}
        self.created = []
        self.cleaned = []
        self.since = None
        self.range_bars = {}

    async def list_targets(self, since):
        self.since = since
        return [
            {**target, "snapshot_complete": target["date"] in self.snapshots}
            for target in self.targets
            if target["date"] >= since
        ]

    async def estimate_storage(self, targets, storage_limit_bytes):
        del targets, storage_limit_bytes
        return {
            "current_bytes": self.current,
            "projected_bytes": self.projected,
            "components": {
                "v1_v2_artifacts": 10,
                "bars": 20,
                "indexes": 30,
                "checkpoints": 40,
            },
        }

    async def create_run(self, resume_run_id=None):
        run_id = resume_run_id or f"run-{len(self.created) + 1}"
        self.created.append(run_id)
        self.runs[run_id] = {"status": "running"}
        return run_id

    async def completed_ranges(self, run_id):
        del run_id
        return set(self.ranges)

    async def get_range(self, ticker, start_date, end_date):
        return self.ranges[(ticker, start_date, end_date)]

    async def record_range(self, run_id, ticker, start_date, end_date, payload):
        del run_id
        self.ranges[(ticker, start_date, end_date)] = payload
        self.range_bars[ticker] = payload["bounded_bars"]

    async def publish_snapshot(self, run_id, date_string, snapshot, watermarks):
        del run_id, watermarks
        self.snapshots[date_string] = snapshot

    async def target_complete(self, run_id, date_string):
        del run_id
        return date_string in self.snapshots

    async def finish_run(self, run_id, report):
        self.runs[run_id] = report

    async def cleanup_ranges(self, run_id):
        self.ranges.clear()
        self.cleaned.append(run_id)


class RemoteV2:
    def __init__(self, bars, splits=None):
        self.bars = bars
        self.splits = splits or {}
        self.calls = []
        self.active = 0
        self.max_active = 0

    async def fetch_range(self, ticker, start_date, end_date):
        self.calls.append((ticker, start_date, end_date))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.001)
        self.active -= 1
        return list(self.bars.get(ticker, []))

    async def fetch_splits(self, ticker):
        return list(self.splits.get(ticker, []))


def _target(day="2024-01-03", tickers=("ABC",), macd=("ABC",), **extra):
    return {
        "date": day,
        "tickers": list(tickers),
        "macd_tickers": list(macd),
        "max_lookback": 20,
        **extra,
    }


@pytest.mark.asyncio
async def test_dry_run_targets_one_year_and_reports_all_storage_components():
    store = MemoryStoreV2([_target()])
    remote = RemoteV2({})
    runner = StockBounceBackfillV2(store, object(), remote)

    report = await runner.run(dry_run=True, as_of=date(2024, 12, 31))

    assert store.since == "2024-01-01"
    assert report["targets"] == ["2024-01-03"]
    assert report["current_bytes"] == 100
    assert report["projected_bytes"] == 200
    assert set(report["components"]) == {
        "v1_v2_artifacts",
        "bars",
        "indexes",
        "checkpoints",
    }
    assert remote.calls == []
    assert store.created == []
    assert store.snapshots == {}


@pytest.mark.asyncio
async def test_apply_refuses_projection_above_seventy_percent_before_writes():
    store = MemoryStoreV2([_target()], current=600, projected=701)
    remote = RemoteV2({})
    runner = StockBounceBackfillV2(store, object(), remote, storage_limit_bytes=1000)

    with pytest.raises(StockBounceStorageLimitError, match="70%"):
        await runner.run()

    assert remote.calls == []
    assert store.created == []
    assert store.snapshots == {}


@pytest.mark.asyncio
async def test_checkpoint_payload_bound_rejects_oversized_history_before_writes():
    from services.stock_bounce.adapters import PostgresBackfillStoreV2

    class NoWritePool:
        def acquire(self):
            raise AssertionError(
                "oversized checkpoint must not acquire a database connection"
            )

    payload = {
        "bars": [{"date": "2024-01-01", "padding": "x" * (3 * 1024 * 1024)}],
        "splits": [],
        "bounded_bars": [],
    }
    store = PostgresBackfillStoreV2(NoWritePool())

    with pytest.raises(ValueError, match="checkpoint.*payload bound"):
        await store.record_range("run", "ABC", None, "2024-01-02", payload)


@pytest.mark.asyncio
async def test_backfill_computes_split_safe_high_and_persists_only_bounded_bars():
    bars = [
        _bar("ABC", "2023-12-01", 150.0),
        _bar("ABC", "2024-01-01", 200.0),
        _bar("ABC", "2024-01-02", 90.0),
        _bar("ABC", "2024-01-03", 101.0),
    ]
    store = MemoryStoreV2([_target(estimated=True)])
    remote = RemoteV2({"ABC": bars}, {"ABC": [{"date": "2024-01-02", "ratio": 2}]})
    runner = StockBounceBackfillV2(store, object(), remote, retry_attempts=1)

    report = await runner.run(as_of=date(2024, 1, 3))

    assert report["unpublished"] == []
    snapshot = store.snapshots["2024-01-03"]
    assert snapshot["rows"][0]["previous_all_time_high"] == 100.0
    assert snapshot["coverage"]["whole_market"]["status"] == "degraded"
    assert snapshot["coverage"]["macd_history"]["status"] == "degraded"
    assert len(remote.calls) == 1
    assert remote.calls[0][1] is None
    assert store.ranges == {}
    assert len(store.range_bars["ABC"]) <= 1261
    assert store.runs[report["run_id"]]["checkpoints_removed"] is True
    assert report["run_id"] in store.runs


@pytest.mark.asyncio
async def test_resume_uses_completed_checkpoint_without_refetch_and_cleans_on_success():
    payload = {
        "bars": [
            _bar("ABC", "2024-01-01", 100.0),
            _bar("ABC", "2024-01-02", 101.0),
        ],
        "splits": [],
        "bounded_bars": [],
    }
    store = MemoryStoreV2([_target(day="2024-01-02")])
    store.ranges[("ABC", None, "2024-01-02")] = payload
    remote = RemoteV2({})
    runner = StockBounceBackfillV2(store, object(), remote)

    report = await runner.run(resume_run_id="resume-me", as_of=date(2024, 1, 2))

    assert report["run_id"] == "resume-me"
    assert remote.calls == []
    assert store.snapshots["2024-01-02"]["rows"][0]["previous_all_time_high"] == 100.0
    assert store.cleaned == ["resume-me"]


@pytest.mark.asyncio
async def test_provider_worker_pool_is_bounded():
    tickers = [f"T{index}" for index in range(6)]
    bars = {
        ticker: [_bar(ticker, "2024-01-01", 100.0), _bar(ticker, "2024-01-02", 101.0)]
        for ticker in tickers
    }
    store = MemoryStoreV2([_target(day="2024-01-02", tickers=tickers, macd=tickers)])
    remote = RemoteV2(bars)
    runner = StockBounceBackfillV2(store, object(), remote, max_concurrency=2)

    report = await runner.run(as_of=date(2024, 1, 3))

    assert report["unpublished"] == []
    assert remote.max_active == 2


@pytest.mark.asyncio
async def test_cli_constructs_v2_runner_and_forwards_resume_and_dry_run(monkeypatch):
    captured = {}

    class Runner:
        def __init__(self, store, local, remote):
            captured["constructed"] = (store, local, remote)

        async def run(self, **kwargs):
            captured["run"] = kwargs
            return {"dry_run": True, "unpublished": []}

    async def pool_stub():
        return "pool"

    monkeypatch.setattr(cli, "StockBounceBackfillV2", Runner)
    monkeypatch.setattr(cli, "connect_postgres", lambda: asyncio.sleep(0))
    monkeypatch.setattr(cli, "close_postgres", lambda: asyncio.sleep(0))
    monkeypatch.setattr(cli, "get_pool", pool_stub)
    args = cli.parse_args(["--dry-run", "--resume-run-id", "run-7"])

    report = await cli.run(args)

    assert report["dry_run"] is True
    assert captured["run"]["dry_run"] is True
    assert captured["run"]["resume_run_id"] == "run-7"


@pytest.mark.asyncio
async def test_postgres_v2_targets_and_storage_estimate_use_local_archive(
    postgres_pool,
):
    from db.crud.published_archive import upsert_artifact
    from services.stock_bounce.adapters import PostgresBackfillStoreV2
    from services.stock_bounce.semantics import build_snapshot

    async def source(day, market_payload=None):
        await upsert_artifact(
            postgres_pool,
            day,
            "market_analytics",
            market_payload or {"SP500": 1},
        )
        await upsert_artifact(
            postgres_pool,
            day,
            "stock_bounce:v1",
            build_snapshot(
                day,
                [
                    {
                        "ticker": "ABC",
                        "open": 100.0,
                        "close": 101.0,
                        "volume": 1000,
                        "open_close_change_pct": 1.0,
                        "bounce": [0.0] * 18,
                    }
                ],
            ),
        )

    await source("2030-02-01")
    await source("2030-02-02", {"by_macd": [{"ticker": "ABC"}]})
    await source("2030-02-03")
    store = PostgresBackfillStoreV2(postgres_pool)
    try:
        targets = await store.list_targets("2030-02-01")
        without_evidence = next(
            item for item in targets if item["date"] == "2030-02-02"
        )
        with_evidence = next(item for item in targets if item["date"] == "2030-02-03")
        assert without_evidence["tickers"] == ["ABC"]
        assert without_evidence["macd_tickers"] == []
        assert without_evidence["macd_history_estimated"] is True
        assert with_evidence["macd_tickers"] == ["ABC"]
        assert with_evidence["macd_history_estimated"] is False
        estimate = await store.estimate_storage(targets, 10_000_000_000)
        assert estimate["projected_bytes"] >= estimate["current_bytes"]
        assert set(estimate["components"]) == {
            "v1_v2_artifacts",
            "bars",
            "indexes",
            "checkpoints",
        }
    finally:
        async with postgres_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM published_dates WHERE session_date = ANY($1::date[])",
                [date(2030, 2, 1), date(2030, 2, 2), date(2030, 2, 3)],
            )
