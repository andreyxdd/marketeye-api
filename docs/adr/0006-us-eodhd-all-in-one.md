# ADR 0006: US market data via EODHD All-in-One

## Status

Accepted

## Context

US equities previously used Polygon.io for OHLCV, ticker universe, session probe, and quarterly operating cash flow (product field `fcf`). Toronto already used EODHD. With an EODHD All-in-One entitlement, keeping two US vendors added CI secrets, fixture formats, and provider divergence without product benefit.

## Decision

Full US cutover to EODHD:

- Bars: `/eod/{T}.US` through `EodhdUSProvider` (same OHLCV cache mixin as TO)
- Universe: `NYSE` + `NASDAQ` exchange-symbol-list, common stock / stock only
- Session probe: `PROBE_TICKER_US` (default `SPY`)
- Product `fcf`: EODHD fundamentals `totalCashFromOperatingActivities` → `format_number_short` (same magnitude + K/M/B string as Polygon-era OCF; not a rename to true freeCashFlow)
- `GOOG` maps to `GOOG.US` (no Polygon-era `GOOG`→`GOOGL` alias)
- CI / runtime market data secret: `EODHD_API_KEY` only (`POLYGON_API_KEY` dropped from workflows)

## Consequences

- `MARKETS["US"].provider` is `eodhd` with `eodhd_exchange: "US"`
- US OHLCV fixtures are EODHD JSON lists, not Polygon aggregate payloads
- Unpublished US session backfill after merge is a separate cron `workflow_dispatch` (not part of this cutover PR)
