# ADR 0008: Combined StockBounce v2 all-time-high archive

## Status

Accepted

## Context

StockBounce v1 provides the legacy 18-period bounce screen and cannot express independent whole-market/MACD-history universes, arbitrary supported lookbacks, or split-safe all-time-high evidence. Mongo retention and point-in-time membership limitations must be visible rather than silently producing partial or survivorship-biased results. Full provider history is too large to retain or query during HTTP reads.

## Decision

Add `stock_bounce:v2` and `/api/stock-bounce/v2` without changing v1 snapshot semantics or v1 query authentication. V2 authenticates only with `X-API-Key`, using constant-time comparison and structured errors.

One canonical v2 snapshot stores the union of both universe memberships, actual T OHLCV, and previous-all-time-high evidence. The combined evaluator loads the snapshot and one set-based batch containing start and T-1 bars. It calculates signed decline over the N sessions ending at T-1, requires positive T open-to-close change and a strict new high, filters before ranking, and independently returns at most 20 rows per universe.

Split events alone rescale comparison prices. Daily publication advances stored high watermarks with new split events and the latest bar. The one-year backfill uses bounded workers and coalesced full-history/split requests to establish this state. Only bounded OHLCV windows and compact state are durable after success; temporary full-range checkpoints support resume and are deleted after a complete run while summaries remain.

Universe coverage and exclusions are tracked independently. Reconstructed or incomplete membership is explicitly `degraded`. Sessions expose the smaller of stored and currently retained v2 coverage, capped at 1,260, so pruning cannot leave stale lookback claims.

Backfill dry-run reports current/projected bytes for v1+v2 artifacts, bars, indexes, and checkpoints. Apply stops before provider calls or writes when projected usage exceeds 70% of `PG_STORAGE_LIMIT_BYTES`. Existing cascade pruning and the PostgreSQL monitor remain authoritative. US Mongo prune eligibility now requires valid v1 and v2 artifacts in addition to generic analytics; TO behavior is unchanged.

## Consequences

Reads are deterministic, provider-independent, and bounded to at most two PostgreSQL queries. Snapshots and ticker-level corporate-action state increase storage and publication work. The first backfill covers 365 calendar days of result sessions, although high verification uses full available provider history. Historical universes reconstructed from retained archives can remain degraded and are not represented as survivorship-free. Production migration/backfill, live provider validation, and legacy credential rotation are operational release gates rather than local test actions.
