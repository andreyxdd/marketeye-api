# ADR 0005: Dense EOD cron probe

## Status

Accepted (2026-07-21)

## Context

Provider EOD publication can lag the original sparse cron schedule. Re-running full
ingest when both markets already have published sessions wastes GitHub Actions time
and provider capacity.

## Decision

1. Schedule `.github/workflows/cronjob.yml` every 30 minutes from 20:00 through
   03:00 UTC; do not cancel an in-progress run.
2. Run a slim `scripts/cron_probe.py` job first. It resolves each market's
   LastCompletedSession and PriorCompletedSession, then emits `needs_work=true`
   when either session is not `is_session_published`.
3. Run full dependency installation and `cronjob.py` only when probe emits work.
   A `workflow_dispatch` `target_date` forces ingest for explicit backfills.
4. Keep the same published-session gate in `cronjob.py`. It skips a market when
   both sessions are already published, protecting manual or future callers that
   bypass the workflow probe.

## Consequences

### Positive

- Session lag can recover within 30 minutes during the overnight window.
- No-work scheduled runs avoid full dependency installation and ticker-universe fan-out.
- In-progress runs finish instead of being cancelled.

### Negative

- Every scheduled slot still makes one short provider probe per market.
- A stale or incomplete published archive intentionally triggers another ingest attempt.
