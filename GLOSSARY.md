# MarketEye API glossary

| Term | Meaning |
|------|---------|
| **StockBounce** | US-only bounce screening. V1 retains legacy tracking/frequencies; v2 returns independent whole-market and MACD-history lists with strict split-adjusted new highs. |
| **Canonical StockBounce snapshot** | Complete versioned full-universe JSONB archive artifact for one retained US session; commit unit for historical and recent reads. V2 rows carry universe membership and previous-all-time-high evidence. |
| **Bounce-ready session** | A US session with a complete canonical snapshot for the requested API version. V2 sessions also expose retained `max_lookback`, capped at 1,260. |
| **Archive completeness** | Per-market set of required published artifacts that makes Mongo source data eligible for pruning. US requires generic analytics and valid StockBounce v1+v2; TO retains its existing requirements. |
| **Exact coverage** | Reconstruction from complete declared/recoverable membership and usable local OHLCV/high evidence without estimated membership or exclusions. |
| **Degraded coverage** | Coverage with estimated historical membership or explicit exclusions. It is visible per v2 universe and is not represented as point-in-time or survivorship-free. |
| **Split-adjusted previous high** | Strict pre-T daily-high maximum rescaled by explicit splits onto T's price basis; dividend-adjusted close prices do not define it. |
| **StockBounce backfill** | Resumable, idempotent materialization of v2 snapshots for the latest 365 calendar days, using bounded coalesced history fetches and a 70% projected-PostgreSQL-storage guard. |

Additional operational terms: see `CONTEXT.md`.
