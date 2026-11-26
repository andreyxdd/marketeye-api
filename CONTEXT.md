# MarketEye API — glossary

| Term | Meaning |
|------|---------|
| **Market** | Trading venue code: `US` or `TO` (Toronto Stock Exchange via EODHD) |
| **AnalyticsService** | Orchestration module for ticker/list/market routes and cron ingest |
| **Calc workspace** | MongoDB hot compute store; rolling delete before ingest for published dates outside the 70-day window |
| **Postgres serving archive** | Hybrid read-model (`published_dates`, `published_artifacts`, `published_tickers`) used for cold reads |
| **OHLCV bar store** | PostgreSQL cache of normalized EOD bars keyed by `(market, ticker, session_date)`; write-through front for EODHD; distinct from **Postgres serving archive** |
| **Storage prune** | At PostgreSQL usage >=85%, alert developer and delete oldest `published_dates` until <=70% (no Drive cold archive) |
| **Mongo storage guard** | At Mongo usage >=85%, alert developer and delete oldest eligible Mongo hot data per market until <=70%; never deletes Postgres rows. US requires analytics plus valid `stock_bounce:v1` and `stock_bounce:v2`; TO keeps existing requirements. Cron uses the same invariant. **TO frequencies lookback:** prune refuses deleting TO `analytics`/`tracking` for dates inside the last 40 published TO trading days (protects T-N / Frequencies history). US prune policy unchanged. |
| **StockBounce archive** | Versioned full-universe JSONB snapshots. V1 preserves legacy screening/tracking; v2 stores both universe memberships and split-safe previous-high evidence for combined arbitrary-lookback reads. Neither API calls EODHD. See ADR 0007 and `docs/adr/0008-stock-bounce-ath-v2.md`. |
| **StockBounce backfill** | `scripts/backfill_stock_bounce.py` targets 365 calendar days of v2 sessions with bounded full-history/split fetches, resumable temporary range checkpoints, and compact retained bars/high watermarks. Dry-run reports artifact/bar/index/checkpoint bytes; apply refuses projections above 70% of `PG_STORAGE_LIMIT_BYTES`; successful runs remove bulky checkpoints. See `docs/handoff/stock-bounce-backfill.md`. |
| **Enrichment policy** | Per-market rules for attaching extras (US: FCF/mentions on hot reads; TO: OHLCV indicators only). Cron publish stubs US mentions to zero |
| **FixtureTradingDay** | Frozen session date for tests (`2024-06-03`) |
| **Fixture tickers** | Fixed US symbol set in Mongo seed (50 large-cap names) |
| **Tier A** | HTTP e2e — client routes, Mongo reads, real CVI aggregation |
| **Tier B** | Calc golden — OHLCV → indicators via `compute_*` |
| **Tier B′** | Provider golden — `MarketDataProvider` implementations vs goldens |
| **Tier C** | Pipeline — ingest → `get_analytics_sorted_by` |
| **MarketDataProvider** | Protocol for exchange-specific OHLCV + ticker universe fetch |
| **LastCompletedSession** | Latest EOD bar date available from the market data provider for a **Market** |
| **PriorCompletedSession** | Trading session immediately before **LastCompletedSession** (not calendar yesterday) |
| **Cron probe** | Slim scheduled preflight: resolves latest sessions for US and TO, checks `is_session_published`, then prints `needs_work=<bool>` (consumed by `scripts/cron_clock.py`) without ticker-universe fan-out |
| **Dense EOD schedule** | Heroku clock dyno (`scripts/cron_clock.py`, Procfile `clock:`) runs Cron probe at minutes 07 and 37 from 20:00 through 02:00 UTC, plus 03:07 (override with env `CRON_SLOTS`). Full ingest (`cronjob.py`) runs only when Cron probe reports work; its Postgres advisory lock prevents overlapping runs. The GitHub Actions workflow is kept for manual `workflow_dispatch` only (optional `target_date`) |
| **Production freshness** | Public `GET /freshness` reports provider expected sessions and US/TO analytics plus US StockBounce v1/v2 archive status. `200` means every component is fresh; stale/unavailable reports return `503`, `Retry-After: 300`, and all responses use `Cache-Control: no-store`. A 60-second server cache bounds provider calls. External UptimeRobot/Telegram setup and manual recovery are documented in `docs/handoff/production-freshness-monitoring.md`; no monitor-driven ingestion |
| **Cron phase timings** | `CronRunReport` records elapsed seconds for every attempted prune/ingest/track/publish phase by market/date and prints them in the final summary. Baseline and comparison commands: `docs/handoff/cron-performance.md` |
| **EodhdUSProvider** | US implementation wrapping EODHD (`.US`, NYSE+NASDAQ) |
| **EodhdTOProvider** | TO implementation wrapping EODHD |
| **Price band** | One of four close-price ranges for Micro screening: `lte5`, `5to10`, `10to20`, `20to50` |
| **Micro screening** | Filter analytics rows by EOD close before top-20 sort |
| **Band tracking** | Cron upserts top-20 tickers into Mongo `tracking` per `(date, criterion, market, price_band)` — unbanded (`price_band` null) plus each of the four bands; ongoing days via cron; historical gaps filled by one-shot **band-frequency backfill** |
| **Band-frequency backfill** | Ops script `scripts/backfill_band_tracking.py` replays `put_top_tickers` then patches frequencies on published artifacts over recent published sessions (default US+TO, 15 trading days). Dates missing Mongo analytics are skipped unless `--reingest-missing` is set (then ingest → track → patch). TO recovery example: `backfill_band_tracking --markets TO --trading-days 40 --reingest-missing`. One-shot ops only — not daily cron auto-repair |
| **TO tracking-density floor** | After TO `put_top_tickers`, cron counts unbanded prior tracking sessions in the frequencies window (`period=25`, `$lt` viewed date). Below floor 10 → `CronRunReport` phase `track_density` failure/alert **and skip `publish_day`** (no blank Frequencies artifact); no auto-backfill. Use band-frequency backfill with `--reingest-missing` to refill |
| **Standard frequency** | T-N appearance string from unbanded tracking (docs with `price_band` null or field absent); used when list reads omit `price_band`. See **T-N / Frequencies** for index meaning |
| **Micro frequency** | Same T-N semantics as Standard, but counted only within the active price band's tracking docs |
| **T-N / Frequencies** | T-1 = most recent *prior* tracking session relative to the viewed date (not the viewed date itself). Built in `get_analytics_frequencies` (`db/crud/tracking.py`) with Mongo `$lt` on `date`, so membership on the viewed date’s top-20 does not appear as T-1. For US unbanded reads, market and band filters both use `$or`; they are combined with `$and` so the market constraint is not overwritten (which previously let Toronto tracking docs interleave and produce even-only T-N / missing T-1). True alternating prior-session membership can still yield even-only strings. **TO** Frequencies need enough Mongo unbanded tracking sessions in the lookback; a sparse hot store (e.g. only two prior sessions) yields shallow T-N even when Postgres published dates look complete — recover via band-frequency backfill `--reingest-missing`, guarded by **TO tracking-density floor** |
| **Deploy revision** | Full git SHA exposed on `/healthz` and `/readyz` as `commit`; resolved from `HEROKU_SLUG_COMMIT` → `SOURCE_VERSION` → `git rev-parse HEAD` → `"unknown"` |

Run instructions: `tests/README.md`.
