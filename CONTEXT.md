# MarketEye API — test glossary

Terms from the local pytest plan (`client_api_e2e_tests`).

| Term | Meaning |
|------|---------|
| **FixtureTradingDay** | Frozen session date for tests (`2024-06-03`); not calendar today |
| **Fixture tickers** | Fixed US symbol set in Mongo seed (50 large-cap names) |
| **Tier A** | HTTP e2e — client routes, Mongo reads, real CVI aggregation |
| **Tier B** | Calc golden — OHLCV → indicators via `compute_*` |
| **Tier B′** | Provider golden — `MarketDataProvider` implementations vs same goldens |
| **Tier C** | Pipeline — `compute_base_analytics_and_insert` → `get_analytics_sorted_by` |
| **MarketDataProvider** | Protocol for exchange-specific OHLCV + ticker universe fetch (`providers/base.py`) |
| **PolygonUSProvider** | US implementation wrapping Polygon.io (`providers/polygon_us.py`) |

Run instructions: `tests/README.md`.
