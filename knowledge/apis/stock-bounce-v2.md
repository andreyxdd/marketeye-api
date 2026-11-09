---
type: api
name: StockBounce all-time-high API v2
status: accepted
---

# StockBounce all-time-high API v2

## Callers

The StockBounce Electron app. The API remains US-only. V2 requires the existing credential in an `X-API-Key` header with constant-time comparison; query-string credentials are not accepted by v2. V1 retains its existing query authentication solely for older clients. The desktop keeps the credential in its main process and never exposes it to the renderer.

## Versioning

URL path versioning under `/api/stock-bounce/v2/`. The new lookback, universe, and all-time-high semantics require a new snapshot/algorithm version rather than additive v1 changes.

## Endpoints

| Method | Path | Intent | Success | Errors |
|--------|------|--------|---------|--------|
| GET | `/api/stock-bounce/v2/sessions` | List sessions with complete v2 data | 200 | 401/403, 422, 503 |
| GET | `/api/stock-bounce/v2/results` | Return both independent top-20 lists | 200 | 401/403, 404, 409, 422, 503 |

### Sessions

Query: optional opaque `cursor` and `limit` (default 200, maximum 500). Response:

```json
{
  "items": [{
    "epoch": 1793059200000,
    "date_string": "2026-10-27",
    "max_lookback": 240
  }],
  "next_cursor": null
}
```

Items are ascending. `max_lookback` is the largest trading-day lookback, capped at 1,260, for which both lists have complete stored session coverage. It initially reflects the one-year backfill and grows as history accumulates. The desktop only offers supported date/lookback combinations. Pagination and the bounded scan behavior follow v1.

### Results

Query: required `date=YYYY-MM-DD` and `lookback=1..1260` trading sessions. One request returns both lists so the two tabs always describe the same inputs.

```json
{
  "schema_version": 2,
  "market": "US",
  "date": "2026-10-27",
  "lookback": 20,
  "whole_market": {
    "rows": [{
      "id": 1,
      "ticker": "XYZ",
      "open": 140.0,
      "high": 148.0,
      "close": 147.0,
      "volume": 1234567,
      "open_close_change_pct": 5.0,
      "lookback_change_pct": -12.5,
      "previous_all_time_high": 146.0
    }],
    "coverage": {
      "status": "exact",
      "universe_provenance": "archived_tickers+local_ohlcv",
      "exclusions_count": 0,
      "unseeded_count": 0
    }
  },
  "macd_history": {
    "rows": [],
    "coverage": {
      "status": "degraded",
      "universe_provenance": "recoverable_macd_membership",
      "exclusions_count": 3,
      "unseeded_count": 1
    }
  }
}
```

For a lookback of N, compare the opening price of the first of N sessions ending at T-1 with T-1's close. N=1 therefore measures T-1 open to close. Require that signed change to be negative and T's open-to-close change to be positive.

The whole-market list uses the declared NYSE/NASDAQ universe for T. The MACD-history list independently uses every recoverable ticker present in MACD App data on or before T-1, including symbols no longer currently listed. Both lists require usable start, T-1, and T bars; exclusions are recorded and never silently filled with partial-period calculations. Within `exclusions_count`, `unseeded_count` identifies tickers still lacking a verified high watermark after scheduled newcomer seeding. It is `null` for legacy snapshots written before this metadata existed, where the count is unknown.

A candidate qualifies only when T's split-adjusted daily high is strictly above every earlier split-adjusted daily high. Split events, not dividend-adjusted close prices, define the adjustment. Unverifiable all-time-high history excludes the candidate. Apply this filter before ranking by T open-to-close change descending and ticker ascending, then return at most 20 rows.

Displayed T open/high/close are the actual session prices. `previous_all_time_high` is expressed on T's split-adjusted basis. `lookback_change_pct` remains signed and is negative for every returned row.

Estimated historical universe reconstruction is allowed but must return `coverage.status="degraded"` and provenance; the desktop shows a clear warning. A valid request with no qualifying rows returns 200 with empty `rows`.

## Error shape

Errors retain the v1 structured `detail` body with `code`, `message`, and `details`.

- `404 SESSION_NOT_FOUND`: date is not a known US session.
- `409 BOUNCE_SESSION_NOT_READY`: either v2 snapshot or required history is incomplete.
- `422`: invalid date, cursor, limit, or lookback, including a lookback above the session's supported coverage.
- `503 BOUNCE_READ_MODEL_UNAVAILABLE`: required archive storage is unavailable.

## Security, performance, and storage

V2 accepts only `X-API-Key`, compares it in constant time, bounds all query inputs, and returns no credential material in errors. Provider credentials and URLs containing credentials are redacted from logs, reports, and checkpoints. The existing embedded desktop credential must be removed and rotated manually before release.

A results read performs at most one snapshot query and one set-based bar query regardless of ticker count or lookback. The representative local performance gate is 6,000 tickers with a 1,260-session lookback at p95 below two seconds. Daily publication uses incremental high-watermark updates; backfill uses bounded concurrency, coalesced ticker ranges, and checkpoints rather than unbounded tasks or full-history in-memory accumulation.

Do not persist full all-time daily bars. Store compact v2 snapshots, the bounded OHLCV window, high watermarks, and split events. Backfill dry-run reports current and projected bytes for v1+v2 artifacts, bars, indexes, and checkpoints; apply refuses projected usage above 70 percent of `PG_STORAGE_LIMIT_BYTES`. Successful runs delete bulky per-range checkpoints while retaining their summaries. Existing cascade pruning removes obsolete session data, and sessions expose only lookbacks still supported by retained history.

## Idempotency and external calls

Both operations are read-only and retry-safe. Historical responses are immutable for a fixed v2 snapshot. Reads never call EODHD. Publication and backfill are idempotent, resumable, and run outside the request path.
