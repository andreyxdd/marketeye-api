# StockBounce backfill runbook

## Deploy first

Apply migrations, including `003_stock_bounce_backfill.sql`, and deploy daily publication plus the shared per-market prune guard before any historical apply. Do not run the all-history command against production until publication failures are visible in cron reporting and US Mongo cleanup is blocked until both analytics and `stock_bounce:v1` are durable.

## Dry-run

```bash
python scripts/backfill_stock_bounce.py --dry-run
```

The report lists retained published US target sessions and archived ticker count without fetching EODHD ranges or writing snapshots/checkpoints. Targets are the currently retained generic US publication set; history is not permanent and remains subject to PostgreSQL pruning.

## Apply and resume

```bash
python scripts/backfill_stock_bounce.py
python scripts/backfill_stock_bounce.py --resume-run-id RUN_ID
python scripts/backfill_stock_bounce.py --force
```

The runner reuses complete local OHLCV history where possible. Otherwise it combines archived tickers with the current EODHD universe, fetches one coalesced range per ticker across target sessions, and records run, target, and ticker-range checkpoints. Resume skips successful ranges and complete targets. `--force` reprocesses sessions that already have snapshots; use it only for deliberate reconstruction.

Exact coverage requires complete archived-universe local evidence. Degraded coverage records `archived_tickers+current_eodhd_universe` provenance and is not point-in-time or survivorship-free. Rows lacking a target bar or 18 preceding trading bars are explicit coverage exclusions, never partial vectors. A session with no usable full-universe rows remains unpublished.

Inspect `published`, `unpublished`, `errors`, and each snapshot's coverage counts/provenance. The command exits nonzero with actionable per-session errors while any target is unpublished. Repeat resume until complete. A live all-history run is an operational acceptance step after local fixture/mocked-provider tests pass; it is not part of CI.

## Read and release gate

Verify `/api/stock-bounce/v1/sessions` paginates every complete snapshot and `/api/stock-bounce/v1/results` handles recent and historical screens/tracking without EODHD calls. Valid no-match screens return 200 with empty rows. Known sessions without snapshots return 409; unknown sessions return 404.

After contract and existing-analytics parity checks, exercise the Windows StockBounce test-tag installer, blockmap, and `updates/bounce-us/latest.yml`. Confirm the four existing update feeds are unchanged before announcing the fifth flavor.
