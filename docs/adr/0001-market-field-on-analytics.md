# ADR 0001: Market field on analytics documents

## Status

Accepted

## Context

MarketEye stores end-of-day stock analytics in MongoDB keyed historically by `(ticker, date)` only. Adding Toronto (TO) alongside US creates ticker collisions (e.g. `RY` on both exchanges). Alternatives: suffixed tickers (`RY.TO`), separate collections, or a `market` dimension.

## Decision

Add a `market` field on each analytics (and tracking) document. Canonical codes: `US`, `TO` (EODHD exchange id). Bare ticker symbols remain in `ticker`. Queries default to `US` when the API omits `market=`.

Legacy US rows are backfilled with `market: "US"`. US queries also match documents where `market` is absent until backfill completes.

## Consequences

- Compound identity becomes `(market, ticker, date)`.
- All CRUD queries and cron jobs must scope by market.
- CVI and bounce remain US-only by filtering `market=US`.
- Client API gains optional `market=` on ticker/list routes.
