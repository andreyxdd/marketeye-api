# MarketEye API — glossary

| Term | Meaning |
|------|---------|
| **Market** | Trading venue code: `US` or `TO` (Toronto Stock Exchange via EODHD) |
| **AnalyticsService** | Orchestration module for ticker/list/market routes and cron ingest |
| **Calc workspace** | MongoDB hot compute store; rolling delete before ingest for published dates outside the 70-day window |
| **Postgres serving archive** | Hybrid read-model (`published_dates`, `published_artifacts`, `published_tickers`) used for cold reads |
| **OHLCV bar store** | PostgreSQL cache of normalized EOD bars keyed by `(market, ticker, session_date)`; write-through front for Polygon/EODHD; distinct from **Postgres serving archive** |
| **Storage prune** | At PostgreSQL usage >=85%, alert developer and delete oldest `published_dates` until <=70% (no Drive cold archive) |
| **Mongo storage guard** | At Mongo usage >=85%, alert developer and delete Mongo hot data for oldest published session (all markets) until <=70%; never deletes Postgres rows |
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
| **Cron probe** | Slim scheduled preflight: resolves latest sessions for US and TO, checks `is_session_published`, then emits GitHub Actions `needs_work` without ticker-universe fan-out |
| **Dense EOD schedule** | GitHub Actions runs every 30 minutes from 20:00 through 03:00 UTC; full ingest runs only when Cron probe reports work (or an explicit `target_date` is dispatched) |
| **PolygonUSProvider** | US implementation wrapping Polygon.io |
| **EodhdTOProvider** | TO implementation wrapping EODHD |
| **Price band** | One of four close-price ranges for Micro screening: `lte5`, `5to10`, `10to20`, `20to50` |
| **Micro screening** | Filter analytics rows by EOD close before top-20 sort |
| **Band tracking** | Cron upserts top-20 tickers into Mongo `tracking` per `(date, criterion, market, price_band)` — unbanded (`price_band` null) plus each of the four bands; forward-only, no backfill |
| **Standard frequency** | T-N appearance string from unbanded tracking (docs with `price_band` null or field absent); used when list reads omit `price_band` |
| **Micro frequency** | Same T-N semantics as Standard, but counted only within the active price band's tracking docs |
| **Deploy revision** | Full git SHA exposed on `/healthz` and `/readyz` as `commit`; resolved from `HEROKU_SLUG_COMMIT` → `SOURCE_VERSION` → `git rev-parse HEAD` → `"unknown"` |

Run instructions: `tests/README.md`.
