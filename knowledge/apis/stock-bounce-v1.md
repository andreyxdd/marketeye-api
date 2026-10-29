---
type: api
name: StockBounce API v1
status: accepted
---

# StockBounce API v1

## Callers

The `bounce-us` MarketEye Electron flavor. The API is US-only; callers do not pass a market parameter.

## Versioning

URL path versioning under `/api/stock-bounce/v1/`. Additive response fields are permitted within v1; changed bounce semantics require a new snapshot/algorithm version and contract review.

## Auth

The existing `api_key` query dependency and its current authentication errors. Public reads never call EODHD.

## Endpoints

| Method | Path | Intent | Success | Errors |
|--------|------|--------|---------|--------|
| GET | `/api/stock-bounce/v1/sessions` | List bounce-ready sessions | 200 | 401/403, 422, 503 |
| GET | `/api/stock-bounce/v1/results` | Screen or track with embedded frequencies | 200 | 401/403, 404, 409, 422, 503 |

### Sessions

Query: optional opaque `cursor` and `limit` (default 200, maximum 500). Response:

```json
{
  "items": [{"epoch": 1793059200000, "date_string": "2026-10-27"}],
  "next_cursor": null
}
```

Items are ascending and include only complete `stock_bounce:v1` snapshots. The desktop loads all pages before enabling date selection. Each request scans at most 1,000 artifacts. When that budget limits progress, `next_cursor` marks the last scanned artifact and may accompany an empty `items` page; otherwise it marks the last returned valid session. Clients must continue whenever `next_cursor` is non-null.

### Screening results

Query: required `date=YYYY-MM-DD`, `period=1..18`, and optional `price_range=all|48to99_99|100to299_99|300to499_99|500to1000` (default `all`). `tickers` is absent.

Legacy ranges become actual inclusive close filters: `48–99.99`, `100–299.99`, `300–499.99`, or `500–1000`. Price selection never changes `period`.

Response:

```json
{
  "schema_version": 1,
  "market": "US",
  "date": "2026-10-27",
  "period": 6,
  "price_range": "100to299_99",
  "rows": [{
    "id": 1,
    "ticker": "XYZ",
    "open": 140.0,
    "close": 147.0,
    "volume": 1234567,
    "open_close_change_pct": 5.0,
    "frequencies": "T-2, T-6"
  }],
  "missing_tickers": [],
  "coverage": "exact"
}
```

Screening preserves legacy selection: negative cumulative change at `bounce[period-1]`, positive current open/close change, and for periods greater than four current change greater than all 18 trailing values. Order is change descending then ticker ascending; maximum 20 rows. Frequencies are period-membership labels for periods 1–17 under the same date and active price filter, not prior-date appearances.

### Tracking results

The same endpoint accepts `tickers=AAPL,MSFT` with 1–20 unique symbols. It returns observations in request order without applying bounce eligibility and reports unavailable symbols in `missing_tickers`. Frequencies describe the tracking response date and active price range. `id` is the one-based display order.

A valid query with no matches returns 200 with `rows: []`.

## Error shape

Errors use non-200 responses with a structured detail body:

```json
{
  "detail": {
    "code": "BOUNCE_SESSION_NOT_READY",
    "message": "StockBounce publication is incomplete for US 2026-10-27",
    "details": {}
  }
}
```

- `404 SESSION_NOT_FOUND`: date is not a known US session.
- `409 BOUNCE_SESSION_NOT_READY`: a known published session lacks a complete bounce snapshot.
- `422`: invalid date, period, price range, cursor, or ticker list.
- `503 BOUNCE_READ_MODEL_UNAVAILABLE`: required archive storage is unavailable.

## Idempotency

All operations are read-only and retry-safe. Historical responses are immutable for a fixed snapshot version; publication and backfill upserts are idempotent and occur outside the request path.
