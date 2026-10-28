# MarketEye API glossary

| Term | Meaning |
|------|---------|
| **StockBounce** | US-only open/close bounce screening, explicit-ticker tracking, and period-membership frequency workflow. |
| **Canonical StockBounce snapshot** | Complete versioned full-universe JSONB archive artifact for one retained US session; commit unit for historical and recent reads. |
| **Bounce-ready session** | A US session with a complete canonical StockBounce snapshot. |
| **Archive completeness** | Per-market set of required published artifacts that makes Mongo source data eligible for pruning. US requires generic analytics and StockBounce; TO retains its existing requirements. |
| **Exact coverage** | Snapshot reconstruction from complete local historical universe and OHLCV evidence. |
| **Degraded coverage** | Snapshot reconstruction that required archived tickers plus the current EODHD universe; not point-in-time or survivorship-free. |
| **StockBounce backfill** | Resumable, idempotent materialization of canonical snapshots for every retained published US session. |

Additional operational terms: see `CONTEXT.md`.
