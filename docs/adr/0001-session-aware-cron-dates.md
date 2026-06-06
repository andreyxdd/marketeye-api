# ADR 0001: Session-aware cron ingest dates

## Status

Accepted (2026-06-05)

## Context

The analytics cronjob ([`cronjob.py`](../../cronjob.py)) historically selected ingest targets using **calendar today and yesterday** in each market's timezone (`get_today_utc_date_in_timezone` + `get_past_date(1)`).

Production benchmark (2026-06-05) showed this wastes most US cron time when the calendar date has no EOD bar yet:

- Requested **2026-06-05** for US: **12,746** Polygon OHLCV fetches, **934.5 s**, **0** computed rows (Polygon's last bar was **2026-06-04**).
- US total for two calendar dates: **1,081.9 s** (~18 min); TO total: **165.9 s**.

The mismatch is enforced in [`services/analytics_service.py`](../../services/analytics_service.py): rows whose computed bar date ≠ requested date are skipped.

## Decision

1. Resolve **LastCompletedSession** and **PriorCompletedSession** per market via a **provider probe** — one short OHLCV fetch for a liquid benchmark ticker (defaults: SPY for US, SHOP for TO).
2. Always ingest **LastCompletedSession**; ingest **PriorCompletedSession** only when `get_missing_tickers` returns a non-empty set for that date (conditional prior).
3. On probe failure: **abort that market**, notify developer, continue other markets (no calendar fallback).
4. Explicit CLI dates (`python cronjob.py YYYY-MM-DD`) bypass session probing for backfills.

## Consequences

### Positive

- Avoids fan-out OHLCV fetches for dates with no provider bar (largest cron cost on non-session calendar days).
- Session dates align with downstream date-mismatch guardrails.
- Per-market failure isolation preserves TO ingest when US probe fails.

### Negative

- One extra provider API call per market per cron run (negligible vs universe pagination).
- Session semantics depend on probe ticker liquidity and provider data lag.
- Requires glossary terms (**LastCompletedSession**, **PriorCompletedSession**) and unit tests around probe parsing.

## Alternatives considered

| Alternative | Rejected because |
|-------------|------------------|
| Calendar today/yesterday | Proven 934s waste / 0 rows on 2026-06-05 |
| Exchange holiday calendar | Maintenance burden; provider bars are source of truth |
| Mongo `max(date)` as session | DB may lag; does not detect partial universe gaps |
| Calendar fallback on probe failure | Reintroduces wasted fetches and silent wrong-date ingest |
