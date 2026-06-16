---
name: Mongo calc engine + Postgres read model
overview: Mongo rolling calc workspace, Heroku Postgres serving archive with publish-before-delete cron, partial Redis removal, no-Drive storage prune monitor, pytest on push to main.
andx_ready: true
domain_grilled: true
source: thread
---

# Postgres read model + backup monitor

Scope: [`marketeye-api`](.) only. Client unchanged. Domain terms grilled; see resolved decisions in thread and glossary updates in step-7.

## Resolved decisions (reference)

| Area | Choice |
|------|--------|
| Atlas emergency | Export first, then delete (manual step-0) |
| Postgres | Heroku Essential-1 (10 GB), `DATABASE_URL` |
| Read model | Hybrid `published_dates` + JSONB artifacts/tickers |
| Redis | Remove read-path cache only; keep external API cache |
| Mongo window | 91d delete after successful publish |
| Publish scope | Lists + top-20 ticker union per day |
| Storage guard | ≥85% → alert + prune oldest published dates to 70% (no Drive export) |
| CI | `pytest tests/ --ignore=tests/calc/test_providers` on **push to main** + dispatch |
| Cron validation | `tests/cron/test_run_crud_ops.py` |

---

## Execution steps

### step-0 — Manual ops gate (prerequisite)

kind: backend
depends: []
touch: [docs/runbooks/]
success: Heroku Postgres Essential-1 provisioned, GitHub `marketeye-api` env secrets set, Atlas under ~400 MB
verification: Manual checklist in `docs/runbooks/postgres-read-model-ops.md` — all boxes checked

**Owner: you (not `/andx-execute` worker).**

Checklist to document in runbook:

1. `heroku addons:create heroku-postgresql:essential-1` on API app; note `DATABASE_URL`
2. GitHub secrets: `DATABASE_URL`, `PG_STORAGE_LIMIT_BYTES=10737418240`, dev email secrets
3. Atlas: run emergency export (after step-2 code exists, or raw JSON fallback); delete oldest data until &lt;400 MB
4. `workflow_dispatch` analytics cron succeeds once

---

### step-1 — Postgres infrastructure

kind: backend
depends: []
touch: [db/postgres.py, db/migrations/, core/settings.py, docker-compose.test.yml, requirements.txt, scripts/apply_migrations.py]
success: Local docker Postgres accepts migrations; `asyncpg` pool connects via `DATABASE_URL`
verification: `docker compose -f docker-compose.test.yml up -d postgres && python scripts/apply_migrations.py && python -c "import asyncio; from db.postgres import get_pool; asyncio.run(get_pool())"`

Schema: `published_dates`, `published_artifacts`, `published_tickers` (see thread plan).

---

### step-2 — Publish service + cron gate

kind: backend
depends: [step-1]
touch: [services/publish_service.py, cronjob.py, .github/workflows/cronjob.yml, .github/workflows/cronjob-manual.yml]
success: `run_crud_ops` publishes snapshots to Postgres before `remove_base_analytics`; publish failure skips Mongo delete and notifies dev
verification: `pytest tests/cron/test_run_crud_ops.py -v` (tests added in step-5; interim: manual dispatch or unit test stub)

Implement `publish_service.publish_day(conn, pg_pool, date, market)`:

- Materialize list/criteria/market responses + enriched tickers (top-20 union)
- Upsert into Postgres tables
- Wire into [`cronjob.py`](cronjob.py) before delete calls

Add `DATABASE_URL` to cron GHA workflows.

---

### step-3 — Read routing + partial Redis removal

kind: backend
depends: [step-2]
touch: [services/read_router.py, services/analytics_service.py, db/crud/analytics.py, main.py, api/endpoints/health.py]
success: Hot dates read Mongo; cold dates read Postgres JSONB; pruned dates 404; `get_dates` unions both stores; `@cache.use_cache_async` removed from `get_analytics_sorted_by`; `/readyz` checks Postgres
verification: `pytest tests/e2e/ -v -k "get_dates or get_analytics"` (cold-path tests added step-5)

Keep [`utils/handle_external_apis.py`](utils/handle_external_apis.py) Redis decorators unchanged.

---

### step-4 — Storage monitor (no cold export)

kind: backend
depends: [step-3]
touch: [scripts/pg_storage_monitor.py, db/crud/published_archive.py, .github/workflows/pg-storage-monitor.yml]
success: At ≥85% storage, script alerts dev and prunes oldest `published_dates` cascade until ≤70%
verification: `pytest tests/storage/test_pg_storage_monitor.py -v` and `python scripts/pg_storage_monitor.py --check-only`

GHA workflow: daily 06:00 UTC + `workflow_dispatch`; `--check-only` supported.

---

### step-5 — Test suite (cron gate + e2e cold path + monitor)

kind: backend
depends: [step-4]
touch: [tests/conftest.py, tests/cron/test_run_crud_ops.py, tests/e2e/test_postgres_cold_path.py, tests/storage/test_pg_storage_monitor.py]
success: `test_run_crud_ops` covers happy path, publish gate, idempotent publish; e2e serves archived date from Postgres only; backup monitor unit tests pass
verification: `docker compose -f docker-compose.test.yml up -d && pytest tests/ --ignore=tests/calc/test_providers -v`

Update [`tests/README.md`](tests/README.md) with `DATABASE_URL` and postgres service.

---

### step-6 — GHA pytest on push to main

kind: backend
depends: [step-5]
touch: [.github/workflows/pytest.yml]
success: Push to `main` runs full pytest suite (excl. provider goldens) with mongo+redis+postgres services
verification: Push to `main` or `workflow_dispatch` → GHA job green

```yaml
on:
  push:
    branches: [main]
  workflow_dispatch:
```

---

### step-7 — Glossary + ADRs

kind: backend
depends: [step-3]
touch: [CONTEXT.md, docs/adr/0002-postgres-read-model.md, docs/adr/0003-postgres-storage-prune.md]
success: CONTEXT.md defines calc workspace + Postgres serving archive + storage prune (no Drive); ADRs document read-model split and prune policy
verification: `test -f docs/adr/0002-postgres-read-model.md && test -f docs/adr/0003-postgres-storage-prune.md && grep -q "Postgres serving archive" CONTEXT.md`

---

## Wave order (for orchestrator)

| Wave | Steps |
|------|-------|
| 0 (manual) | step-0 |
| 1 | step-1 |
| 2 | step-2 |
| 3 | step-3 |
| 4 | step-4 |
| 5 | step-5 |
| 6 | step-6 |
| 3+ | step-7 (parallel with step-4+ after step-3) |

---

## Next

- Complete **step-0** manual ops gate
- `/andx-execute` on `/Users/andreyxdd/Dev/freelance/market-eye/marketeye-api/.claude/plans/postgres-read-model.plan.md`
