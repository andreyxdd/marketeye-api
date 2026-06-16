# ADR 0002: PostgreSQL serving archive read model

## Status

Accepted (2026-06-16)

## Context

MongoDB remains the calculation workspace for ingest and enrichment, but it cannot hold long retention safely on the current plan. API clients still need historical reads after hot-window cleanup.

We need:

- Publish-before-delete safety gate in cron.
- Cold-read serving path independent of Mongo hot retention.
- Minimal schema complexity with deterministic query keys.

## Decision

Adopt PostgreSQL as serving archive with a hybrid schema:

- `published_dates(session_date, market)` - publish index and prune anchor.
- `published_artifacts(session_date, market, artifact_key, payload JSONB)` - list and market payloads.
- `published_tickers(session_date, market, ticker, payload JSONB)` - enriched ticker payloads.

Publishing flow:

1. Ingest base analytics into Mongo.
2. Build top-list artifacts for all price bands + criteria, plus US market snapshot.
3. Build ticker payloads from union(top-20 lists).
4. Upsert artifacts/tickers into PostgreSQL.
5. Only after publish success, prune Mongo rows older than 91 days.

Read flow:

- Hot dates (within `MONGO_HOT_WINDOW_DAYS`) -> Mongo.
- Cold dates -> PostgreSQL JSONB artifacts/tickers.
- Missing cold payload -> HTTP 404.

## Consequences

### Positive

- Delete safety: no Mongo prune unless publish succeeds.
- Cold reads stay available after hot-window cleanup.
- Idempotent upserts support reruns/backfills.

### Negative

- Read router adds complexity and dual-store behavior.
- JSONB payloads keep shape flexible but reduce strict relational typing.
- PostgreSQL availability now part of readiness and cron reliability.
