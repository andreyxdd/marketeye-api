# ADR 0004: Mongo storage guard with pre-ingest prune

## Status

Accepted (2026-06-18)

## Context

MongoDB is the hot calc workspace with a finite storage budget (`MONGO_STORAGE_LIMIT_BYTES`, default 512 MiB). The previous cron flow deleted Mongo rows **after** publish and retained a 91-day window, which allowed storage to grow when publish enriched US rows with scrapes-backed mentions.

Constraints:

- Bound Mongo usage with automated monitoring and emergency prune.
- Never delete PostgreSQL published archive rows from the Mongo monitor.
- Only drop Mongo hot data for session dates already present in `published_dates`.
- Shrink the rolling hot window to 70 days.

## Decision

1. **Pre-ingest retention** — Before ingest for each cron date, if `date_to_remove` is published in Postgres for that market, delete Mongo `analytics` and `tracking` for that market/date. Post-publish Mongo deletes are removed.

2. **Publish enrichment** — Cron `publish_day` passes `include_mentions=False`, stubbing US mention fields to zero (same as TO) to avoid scrapes reads during publish.

3. **Emergency monitor** — `scripts/mongo_storage_monitor.py` checks `dbStats` ratio against `MONGO_STORAGE_LIMIT_BYTES`. At ratio >= 0.85, notify developer; if not `--check-only`, repeatedly prune Mongo analytics+tracking for the globally oldest `published_dates` session (all markets) until ratio <= 0.70.

4. **Cron startup** — After Postgres connect, run the Mongo storage monitor before per-market ingest.

## Consequences

### Positive

- Mongo growth is bounded without touching Postgres archive rows.
- Published-gated prune prevents dropping unpublished hot data.
- Cron publish path avoids scrapes collection reads.

### Negative

- Published US cold snapshots store zeroed mention fields from cron publish (live hot reads still enrich mentions).
- Emergency prune deletes Mongo hot data for published dates across all markets on the oldest session date.
