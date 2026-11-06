# Knowledge log

## 2026-11-06 — StockBounce all-time-high v2

Accepted a combined desktop request returning independent whole-market and MACD-history top-20 lists. V2 uses signed open-to-close lookback decline through T-1, positive T open-to-close rise, and a strict split-adjusted daily-high breakthrough filtered before ranking. The UI limits lookbacks to complete coverage up to 1,260 trading sessions; initial result backfill covers one year, while high verification uses full available history. Estimated historical universes require visible degraded-coverage warnings. V1 remains for older clients. Contracts: `knowledge/apis/stock-bounce-v2.md` and `knowledge/modules/stock-bounce-v2.md`.

The implementation uses separate reviewer-facing backend and desktop branches with draft-PR/no-merge execution when explicitly invoked with `--mr`. V2 adds header-only credential handling, bounded set-based reads and a p95 benchmark, incremental high updates, bounded backfill concurrency, compact retention instead of full-history storage, projected-size blocking above 70 percent of the configured PostgreSQL limit, and checkpoint cleanup.
