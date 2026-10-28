# ADR 0007: Canonical StockBounce archive and per-market prune safety

## Status

Accepted

## Context

The legacy US bounce client coupled close-price ranges to lookback periods, queried Mongo for every frequency period, and had no durable historical read model after Mongo pruning. Generic analytics publication could finish while bounce data was absent, making source-data cleanup unsafe.

## Decision

Store one complete full-universe `stock_bounce:v1` JSONB artifact per retained US session in `published_artifacts`. A snapshot contains legacy-compatible 18-value vectors and coverage metadata. One pure StockBounce implementation owns vector construction, screening, tracking, ordering, and period-membership frequencies for ingestion, daily publication, backfill, and reads.

The API reads only this archive. It does not call EODHD or fall back to Mongo. The backfill resumes run/target/ticker-range checkpoints, coalesces ticker history requests across sessions, and marks reconstruction degraded when archived tickers must be combined with the current EODHD universe.

Mongo prune eligibility uses one per-market archive-completeness interface in cron and the emergency monitor. US requires generic analytics and a complete StockBounce artifact. TO retains its previous artifact requirements. Unsafe market/date rows are skipped rather than forcing safe markets to wait or bypassing protection.

## Consequences

Snapshots trade storage and parse cost for one immutable source supporting every period, real close filter, tracked ticker set, and embedded frequencies. Historical coverage lasts only as long as existing PostgreSQL retention. Current-universe backfills are explicitly degraded and are not survivorship-free. Publication and the prune guard must be deployed before historical backfill.
