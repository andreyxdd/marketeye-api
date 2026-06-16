# ADR 0003: PostgreSQL storage prune without cold export

## Status

Accepted (2026-06-16)

## Context

Serving archive lives in PostgreSQL with finite storage budget (`PG_STORAGE_LIMIT_BYTES`, default 10 GiB). Previous design discussed offloading old snapshots to Google Drive or Heroku backup export, but operational scope was reduced.

Constraints:

- No Google Drive archive path.
- No Heroku PG backup export path.
- Keep archive self-contained with bounded storage.

## Decision

Implement storage monitor and prune loop:

- Daily monitor checks `pg_database_size(current_database()) / PG_STORAGE_LIMIT_BYTES`.
- At ratio >= 0.85:
  - notify developer by email.
  - if not `--check-only`, delete oldest `session_date` from `published_dates` (cascade) repeatedly.
- Stop when ratio <= 0.70 or archive is empty.

Deletion unit is session date (all markets for that date), preserving simple deterministic retention behavior.

## Consequences

### Positive

- Fully automated bounded-storage policy.
- No dependence on third-party cold storage pipelines.
- Operationally simple and testable.

### Negative

- Old archive data is permanently dropped after prune.
- No built-in cold restore path for pruned dates.
- Developer alerting is necessary to track retention impact.
