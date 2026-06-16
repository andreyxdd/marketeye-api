# MarketEye API — glossary

| Term | Meaning |
|------|---------|
| **Market** | Trading venue code: `US` or `TO` (Toronto Stock Exchange via EODHD) |
| **AnalyticsService** | Orchestration module for ticker/list/market routes and cron ingest |
| **Calc workspace** | MongoDB hot compute store; rolling delete after successful publish (91-day window) |
| **Postgres serving archive** | Hybrid read-model (`published_dates`, `published_artifacts`, `published_tickers`) used for cold reads |
| **Storage prune** | At PostgreSQL usage >=85%, alert developer and delete oldest `published_dates` until <=70% (no Drive cold archive) |
| **Enrichment policy** | Per-market rules for attaching extras (US: FCF/mentions; TO: OHLCV indicators only) |
| **FixtureTradingDay** | Frozen session date for tests (`2024-06-03`) |
| **Fixture tickers** | Fixed US symbol set in Mongo seed (50 large-cap names) |
| **Tier A** | HTTP e2e — client routes, Mongo reads, real CVI aggregation |
| **Tier B** | Calc golden — OHLCV → indicators via `compute_*` |
| **Tier B′** | Provider golden — `MarketDataProvider` implementations vs goldens |
| **Tier C** | Pipeline — ingest → `get_analytics_sorted_by` |
| **MarketDataProvider** | Protocol for exchange-specific OHLCV + ticker universe fetch |
| **LastCompletedSession** | Latest EOD bar date available from the market data provider for a **Market** |
| **PriorCompletedSession** | Trading session immediately before **LastCompletedSession** (not calendar yesterday) |
| **PolygonUSProvider** | US implementation wrapping Polygon.io |
| **EodhdTOProvider** | TO implementation wrapping EODHD |
| **Price band** | One of four close-price ranges for Micro screening: `lte5`, `5to10`, `10to20`, `20to50` |
| **Micro screening** | Filter analytics rows by EOD close before top-20 sort |
| **Deploy revision** | Full git SHA exposed on `/healthz` and `/readyz` as `commit`; resolved from `HEROKU_SLUG_COMMIT` → `SOURCE_VERSION` → `git rev-parse HEAD` → `"unknown"` |

Run instructions: `tests/README.md`.
