# StockBounce v2 backfill runbook

## Scope and release order

`scripts/backfill_stock_bounce.py` reconstructs `stock_bounce:v2` snapshots. It targets published US sessions in the 365-calendar-day window ending when the command starts. It does not alter v1 screening or v1 query authentication.

Before an apply, deploy migrations through `004_stock_bounce_v2.sql` and the daily publishers. The v2 publisher requires durable high-watermark and split state established by the backfill; it never downloads full history in the daily or request path. US Mongo cleanup remains blocked until generic analytics, valid `stock_bounce:v1`, and valid `stock_bounce:v2` artifacts are durable. TO cleanup is unchanged.

Live provider imports and production applies are post-deploy operational gates. Do not run them in CI or as part of local implementation verification.

## Dry-run and storage gate

```bash
python scripts/backfill_stock_bounce.py --dry-run
```

Dry-run reads local targets and storage statistics only. It performs no EODHD request and creates no run, checkpoint, bar, or snapshot. The report includes `since`, target sessions, ticker count, `current_bytes`, `projected_bytes`, `limit_bytes`, and current/projected components for `v1_v2_artifacts`, `bars`, `indexes`, and `checkpoints`.

Apply refuses to create a run or fetch provider data when projected usage is greater than 70% of `PG_STORAGE_LIMIT_BYTES`. Reduce retained data or increase the configured limit after operational review; do not bypass the guard with `--force`.

## Apply and resume

```bash
python scripts/backfill_stock_bounce.py
python scripts/backfill_stock_bounce.py --resume-run-id RUN_ID
python scripts/backfill_stock_bounce.py --force
```

The runner uses a fixed-size worker pool. For each required ticker it makes one coalesced full-history request through the latest target and one split-history request. Full histories exist in memory only in a worker and in a temporary per-range checkpoint. PostgreSQL retains only the bounded bars needed for up to 1,260 prior sessions plus the target window, explicit split events, compact high watermarks, memberships, and snapshots.

A ticker is advanced chronologically so every target row receives the strict pre-T high on T's split-adjusted basis. Dividend-adjusted closes are not used. Estimated source universes and exclusions set the affected universe's coverage to `degraded`; the two coverage objects are independent.

Resume skips completed targets and reuses completed range payloads without provider refetching. Failed targets retain successful checkpoints for retry. A fully successful run deletes its bulky range payloads but retains the run/target summary and sets `checkpoints_removed=true`. `--force` deliberately reconstructs already complete snapshots and is not a storage-guard override.

Inspect `published`, `unpublished`, `errors`, storage bytes, and `checkpoints_removed`. The command exits nonzero while any target is unpublished or the storage guard refuses the apply. Provider credentials and credential-bearing URLs are redacted from reports and errors.

## Reads and retention

Verify `/api/stock-bounce/v2/sessions` and `/api/stock-bounce/v2/results` using only `X-API-Key`. A result read uses one snapshot query and, for a nonempty snapshot, one set-based start/T-1 bar query. It never calls EODHD. Unknown sessions return 404, incomplete data returns 409, unsupported retained lookbacks return 422, and valid no-match requests return two empty lists.

`max_lookback` is capped at 1,260 and calculated from the currently retained valid v2 session chain, not from provider history depth. PostgreSQL pruning therefore lowers supported coverage as old snapshots disappear. Existing published-date cascade and OHLCV pruning remain authoritative; high watermarks, splits, and membership state are reusable ticker-level evidence rather than full all-time bar archives.

A live production backfill, real EODHD response validation, and the pre-release rotation/removal of the legacy embedded desktop credential remain manual release gates.
