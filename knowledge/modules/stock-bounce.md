---
type: module
name: StockBounce canonical snapshot module
status: accepted
---

# StockBounce canonical snapshot module

## Problem

Provide the legacy US open/close bounce screen, explicit-ticker tracking, and period-membership frequencies for recent and historical sessions without coupling price filters to lookback periods or issuing one database query per frequency period.

## Callers

The versioned FastAPI adapter, daily US publication, the historical backfill runner, and contract/golden tests.

## Interface

```text
sessions(cursor?, limit?) -> ascending bounce-ready sessions
evaluate(snapshot, date, period=1..18, price_range=all|legacy-range, tickers?=1..20)
  -> ordered ready-to-render rows with embedded frequencies and missing_tickers
publish_us_session(date) -> complete canonical snapshot or a recorded failure
backfill_all_published_us_sessions(resume_run_id?, dry_run?, force?) -> run report
```

A canonical PostgreSQL `published_artifacts` row uses key `stock_bounce:v1` and contains the whole declared US universe for one session. Each row contains `ticker`, `open`, `close`, `volume`, `open_close_change_pct`, and the legacy ordered `bounce` vector. Coverage metadata records universe provenance, counts, exclusions, and whether reconstruction is `exact` or `degraded`.

The snapshot is the commit unit: readers see it only after all required rows and coverage metadata are durable. Existing PostgreSQL retention and `ON DELETE CASCADE` semantics continue to apply.

Archive completeness is a separate deep safety module with one per-market prune invariant. Cron and the emergency monitor both use it: US requires generic analytics and `stock_bounce:v1`; TO retains its existing requirements. Safe TO pruning may proceed while unsafe US data remains, and oldest-eligible-date selection must skip unsafe market/date rows rather than bypassing the invariant.

## Usage example

A screening request for period 6 and `100to299_99` loads one canonical snapshot, applies the real inclusive close filter `100 <= close <= 299.99`, requires `bounce[5] < 0` and positive current open/close change, applies the legacy long-period rule, ranks by change descending and ticker ascending, and returns the top 20 with frequencies for periods 1–17 computed from the same snapshot and price filter.

A tracking request supplies up to 20 tickers instead of a screen. It preserves request order, returns available observations without applying bounce eligibility, computes frequencies for the tracking date and active price filter, and reports missing symbols separately.

## Hidden complexity

- One pure implementation owns legacy vector construction, screening, tracking, price filtering, long-period selection, deterministic ordering, and frequencies. Existing analytics ingestion, daily publication, backfill, and reads share it; legacy Mongo aggregation is only a golden-parity oracle.
- Canonical snapshot validation, coverage, and versioned archive keys.
- Daily publication and the shared per-market archive-completeness prune invariant.
- Archive-first snapshot access and bounce-ready session-state interpretation stay inside StockBounce; the generic analytics hot/cold router remains untouched.
- Resumable ticker/range-coalesced EODHD backfill, checkpoints, retries, and idempotent session materialization live in a deep backfill implementation, not its thin command adapter.
- A strict local-bars adapter distinguishes unavailable storage, incomplete history, and legitimately absent bars without changing the live provider's fail-open cache behavior.
- Historical-universe limitations and explicit degraded-coverage provenance.

In-process semantics are tested directly with OHLCV fixtures and canonical snapshots. MongoDB/PostgreSQL adapters use local integration tests, including one shared prune-invariant matrix. The owned HTTP interface uses FastAPI contract tests. EODHD is a true external dependency and uses mocked or recorded responses.

## Trade-offs

A full-universe JSONB snapshot is larger and costs more parse/CPU work than a top-20 response artifact. It is less flexible for ad hoc SQL than normalized observations. Existing archive pruning means full history means every currently retained session, not permanent retention. Current EODHD symbol lists are not point-in-time universes, so degraded backfills are not survivorship-free.

## Chosen because

One canonical snapshot supports every period, real price range, tracked ticker set, and frequency query without 90 precomputed period/range combinations. Two read operations hide substantially more complexity than a normalized multi-table model requires callers to understand, while keeping publication and backfill local to this module.
