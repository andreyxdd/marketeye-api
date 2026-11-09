---
type: module
name: StockBounce all-time-high snapshot module
status: accepted
---

# StockBounce all-time-high snapshot module

## Problem

Provide two independent US bounce lists for any supported trading-day lookback: the declared NYSE/NASDAQ universe and every recoverable stock ever present in MACD App data. Return only positive T risers whose split-adjusted T daily high exceeds all earlier daily highs, while preserving honest historical-universe coverage and keeping provider calls out of reads.

## Callers

The versioned FastAPI v2 adapter, daily US publication, the historical backfill runner, and contract/golden tests. The Electron client calls only the combined v2 results operation.

## Interface

```text
sessions(cursor?, limit?) -> ascending v2-ready sessions with max_lookback
evaluate_session(date, lookback=1..1260) -> whole_market and macd_history lists
publish_us_session(date) -> complete v2 snapshot or a recorded failure
backfill(since=one year, resume_run_id?, dry_run?, force?) -> run report
```

A canonical PostgreSQL `published_artifacts` row uses key `stock_bounce:v2`. It contains the union of both declared universes for one session, per-row universe membership, actual T OHLCV, split-adjustment evidence, and the split-adjusted previous all-time high. Separate coverage metadata describes each universe's provenance, counts, and exclusions. The snapshot remains the commit unit.

The evaluator reads the v2 snapshot plus stored start/T-1 bars, computes signed lookback change and positive T open/close change, applies the strict new-high test, then ranks and truncates each list independently. One combined read hides universe reconstruction, split handling, history completeness, filtering, and ordering from the HTTP adapter and desktop.

The initial backfill targets the most recent 365 calendar days of recoverable sessions. All-time-high verification still uses the provider's full available daily history and explicit split events; only the supported result-session range is limited to one year. The backfill retains reusable bars/checkpoints and per-session high watermarks rather than downloading history during reads. A bounded pre-publication seeder gives current analytics newcomers a strict pre-T watermark from full provider history; failures and symbols without pre-T bars remain visible as unseeded exclusions without blocking seeded tickers. Daily publication then advances the same high-watermark state and applies new split events before publishing.

## Usage example

For T with lookback 20, a whole-market row must have a negative change from the first of the 20 sessions ending at T-1 to T-1's close, a positive T open-to-close change, and a split-adjusted T high strictly above its previous all-time high. The same rules independently screen the MACD-history universe. Each list is ordered by T change descending and ticker ascending after the new-high filter.

## Hidden complexity

- Point-in-time and historical MACD membership reconstruction, including explicit degraded coverage when only an estimated universe is recoverable.
- Split-only price adjustment and split-event rescaling of stored high watermarks; dividend adjustments do not affect the comparison.
- Full-history all-time-high verification without full-history queries or provider calls on the request path.
- Arbitrary supported lookbacks from stored bars rather than precomputed top-20 artifacts for every period.
- Resumable one-year session backfill, daily publication, idempotent upserts, and archive-completeness/prune protection for `stock_bounce:v2`.
- Actual session prices for display versus split-adjusted values used only for comparisons.

In-process semantics use independently calculated OHLCV/split fixtures. PostgreSQL adapters use local integration tests. The owned HTTP interface uses FastAPI contract tests. EODHD history and split responses are mocked or recorded. V1 behavior remains unchanged as a compatibility contract.

## Non-functional contract

- V2 reads use at most one snapshot query and one set-based bar query, never per-ticker statements or provider calls. The representative local gate is 6,000 tickers with a 1,260-session lookback at p95 below two seconds. Daily publication advances high watermarks incrementally; backfill uses coalesced ranges and bounded concurrency.
- Persist compact snapshots, the bounded OHLCV window, per-ticker high watermarks, and split events rather than full all-time bars. Dry-run reports current and projected database bytes across snapshots, bars, indexes, and checkpoints; apply refuses projected usage above 70 percent of `PG_STORAGE_LIMIT_BYTES`. Successful runs retain their summary but discard bulky per-range checkpoints. Existing cascade pruning remains authoritative, and available lookbacks shrink honestly when retention removes history.
- V2 accepts only header credentials with constant-time comparison. Responses, logs, exceptions, reports, and checkpoints redact credentials. The desktop uses main-process environment configuration and no embedded credential; rotating the previously embedded legacy key is a manual pre-release requirement.

## Trade-offs

V2 snapshots and high-watermark state add storage and publication work but make arbitrary-lookback reads deterministic and provider-independent. Estimated historical universes can produce useful old-date results but are not survivorship-free and must always be visible as degraded. Initially only one year of result sessions is imported even though the interface permits up to five years when coverage grows.

## Chosen because

One canonical v2 snapshot and one combined evaluator support both tabs with identical date/lookback inputs and no duplicate frontend orchestration. Storing membership and previous-high evidence at each session preserves historical reads without exposing ticker-list or corporate-action complexity to callers.
