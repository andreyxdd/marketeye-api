# Knowledge log

## 2026-11-18 — TO Frequencies blank on latest (density + prune)

**Symptom:** Latest TO session returned 0/20 nonempty Frequencies for Standard (`:all`) and Micro (`lte5`). Postgres dates ≤2026-11-13 still good; Mongo lookback mostly gone.

**Cause:** `count_prior_unbanded_tracking_sessions` = 0 after Mongo prune wiped TO tracking inside the frequencies window; cron still called `publish_day` after `track_density` alert → blank artifact.

**Guards:** (1) Density fail blocks `publish_day` for that TO date. (2) Mongo prune refuses TO `analytics`/`tracking` deletes for dates inside the last 40 published TO trading days.

**Recovery (unchanged):** `python scripts/backfill_band_tracking.py --markets TO --trading-days 40 --reingest-missing` (dry-run first). After deploy, verify Standard (no `price_band`) and Micro (`lte5`) on latest.

## 2026-11-17 — TO Frequencies shallow history (tracking density)

**Symptom:** Standard/Micro TSX Frequencies showed only ~T-1/T-2 (“two sessions”) while US looked normal.

**Cause:** TO Mongo hot `analytics`/`tracking` covered only ~2026-11-11..13 in the frequencies lookback, so `get_analytics_frequencies` found two prior unbanded TO docs. Not a T-N formula bug, not the client, not the US `$or` market-filter clobber (fixed earlier).

**Recovery:** `python scripts/backfill_band_tracking.py --markets TO --trading-days 40 --reingest-missing` (dry-run first). Reingests missing analytics, then `put_top_tickers`, then patches published frequencies.

**Guard:** Cron TO tracking-density floor — after `put_top_tickers`, if prior unbanded sessions in the `period=25` window are below 10, record `track_density` on `CronRunReport` and skip `publish_day` (alert/fail; no auto-backfill).

## 2026-11-06 — StockBounce all-time-high v2

Accepted a combined desktop request returning independent whole-market and MACD-history top-20 lists. V2 uses signed open-to-close lookback decline through T-1, positive T open-to-close rise, and a strict split-adjusted daily-high breakthrough filtered before ranking. The UI limits lookbacks to complete coverage up to 1,260 trading sessions; initial result backfill covers one year, while high verification uses full available history. Estimated historical universes require visible degraded-coverage warnings. V1 remains for older clients. Contracts: `knowledge/apis/stock-bounce-v2.md` and `knowledge/modules/stock-bounce-v2.md`.

The implementation uses separate reviewer-facing backend and desktop branches with draft-PR/no-merge execution when explicitly invoked with `--mr`. V2 adds header-only credential handling, bounded set-based reads and a p95 benchmark, incremental high updates, bounded backfill concurrency, compact retention instead of full-history storage, projected-size blocking above 70 percent of the configured PostgreSQL limit, and checkpoint cleanup.
