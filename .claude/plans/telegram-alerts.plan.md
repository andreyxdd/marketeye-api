---
name: Telegram alerts migration
overview: Replace SMTP developer email alerts with Telegram Bot API notifications across cron, storage monitor, scraping, API endpoint, CI workflows, healthcheck monitor, and API freshness checks.
andx_ready: true
source: thread
---

# Telegram alerts migration

Scope: [`marketeye-api`](.) only. Replaces `utils/handle_emails.py` (smtplib) with `utils/handle_telegram.py` (Telegram Bot API).

## Resolved decisions

| Area | Choice |
|------|--------|
| Transport | Telegram Bot API `sendMessage` to channel |
| Prefix | `[Market Eye] {subject}` |
| Settings | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID` |
| Message limit | Truncate at 4096 chars |
| Health probe | `/healthz` + `/readyz` on `PING_URL` (replaces `pinger.py`) |
| Freshness check | `test-api.py` exits non-zero + Telegram alert on stale date |

---

## Execution steps

### step-1 — Telegram notifier module + settings

kind: backend
touch: [utils/handle_telegram.py, core/settings.py, tests/utils/test_handle_telegram.py]
success: `notify_developer(body, subject)` posts to Telegram with app prefix; unit tests pass

### step-2 — Migrate callers

kind: backend
depends: [step-1]
touch: [cronjob.py, scrapingjob.py, scripts/pg_storage_monitor.py, api/endpoints/notifications.py]
success: All runtime callers import `handle_telegram`; `pinger.py` and `test-api.py` untouched

### step-3 — Update test stubs

kind: test
depends: [step-2]
touch: [tests/helpers/stubs.py, tests/e2e/conftest.py]
success: E2E/cron/storage tests patch `handle_telegram.notify_developer`

### step-4 — Remove email

kind: backend
depends: [step-3]
touch: [utils/handle_emails.py, core/settings.py, README.md, docs/adr/0003-postgres-storage-prune.md]
success: No `handle_emails` or `DEV_*` settings remain

### step-5 — CI workflows (cron/storage)

kind: ci
depends: [step-4]
touch: [.github/workflows/cronjob.yml, cronjob-manual.yml, pg-storage-monitor.yml]
success: Workflows use Telegram secrets; `additional_dev_receiver_email` input removed

### step-6 — Healthcheck monitor

kind: backend
depends: [step-5]
touch: [scripts/healthcheck_monitor.py, tests/scripts/test_healthcheck_monitor.py, .github/workflows/healthcheck.yml]
delete: [pinger.py, .github/workflows/pinger.yml]
success: Cron `*/20` probes health endpoints; failure notifies + exit 1

### step-7 — test-api freshness

kind: backend
depends: [step-6]
touch: [test-api.py, tests/scripts/test_test_api.py, .github/workflows/test-api.yml]
success: Freshness script uses Telegram, clearer subject/body, non-zero exit on failure

---

## Verification

```bash
pytest tests/utils/test_handle_telegram.py -v
pytest tests/e2e/test_notify_developer.py tests/cron/test_run_crud_ops.py tests/storage/test_pg_storage_monitor.py -v
rg 'handle_emails|DEV_' --glob '!*.plan.md'
pytest tests/scripts/test_healthcheck_monitor.py tests/scripts/test_test_api.py -v
```

## Secrets (GitHub `marketeye-api` environment)

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHANNEL_ID`

Remove obsolete `DEV_*` secrets after deploy.
