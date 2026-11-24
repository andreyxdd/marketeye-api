# Production freshness monitoring and rollout

This runbook configures independent detection for stale published sessions. It does not add an ingestion runner or automatic recovery. GitHub Actions remains the only analytics ingestion path, and recovery remains a deliberate `workflow_dispatch`.

## Prerequisites and disclosure boundary

- Deploy an API revision that includes public `GET /freshness` before enabling the monitor.
- Use the existing development Telegram bot and existing alerts channel. No new bot or channel is required.
- Store the Telegram bot token only in UptimeRobot's protected webhook URL/configuration. Do not put it in this repository, monitor labels, Telegram message text, shell history, or GitHub workflow logs.
- UptimeRobot custom webhooks require a plan that supports them (currently Team/Scale). Confirm the subscription before rollout; the free tier is not sufficient for this design.
- The endpoint needs no API key and returns only aggregate statuses and market session dates. It never triggers ingest, repair, redispatch, or notification work.

## Deployment order

1. Review and merge the API, cron workflow, and timing changes together. Deploy the API revision to Heroku, then confirm `/healthz` and `/readyz` retain their existing behavior.
2. Verify the live endpoint before creating alerts:

   ```bash
   curl -i https://marketeye-api.herokuapp.com/freshness
   ```

   A fully published latest completed session must return `200`, `"status": "fresh"`, and `Cache-Control: no-store`. A stale or unavailable component must return `503`, the same report shape, `Cache-Control: no-store`, and `Retry-After: 300`. Do not treat a green `/readyz` response as proof of freshness.
3. Let the updated GitHub workflow run normally. Record the first probe and ingest cache misses and later cache hits using `docs/handoff/cron-performance.md`. A no-work run exercises only the probe job; do not force a redundant ingest merely to benchmark the ingest cache.
4. Configure the UptimeRobot monitor and webhook alert contacts below. Keep the monitor paused until both webhook payloads have been tested.
5. Enable the monitor, then observe it through one complete next-trading-session publication cycle before relying on it as the incident boundary.

## UptimeRobot HTTP monitor

Create one HTTP(s) monitor with these settings:

| Setting | Value |
|---|---|
| Friendly name | `MarketEye production freshness` |
| URL | `https://marketeye-api.herokuapp.com/freshness` |
| Check interval | **5 minutes** |
| Down-alert delay | **60 minutes of continuous non-200 responses** |
| Request method | `GET` |
| Authentication / query / body | None |
| Certificate validation | Enabled |

The monitor must treat any non-200 response as down. Do not configure a keyword-only success check: a `503` report is intentionally diagnosable and must still alert. The 60-minute delay is continuous-down grace, not a suppression rule for intermittent failures. The endpoint's 60-second server-side cache is shorter than the five-minute check interval; `Cache-Control: no-store` still prevents client/intermediary reuse.

## Direct Telegram down/up webhooks

Create two custom webhook alert contacts, one for down alerts and one for recovery/up alerts. Attach only the down contact to down notifications and only the up contact to recovery notifications on this monitor.

Common configuration for both contacts:

| Setting | Value |
|---|---|
| Request method | `POST` |
| URL | `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/sendMessage` |
| Content type | `application/json` |
| Credential storage | UptimeRobot protected webhook configuration only |

Replace `<TELEGRAM_BOT_TOKEN>` and `<TELEGRAM_CHANNEL_ID>` in UptimeRobot, never in a committed file. Use the existing alerts channel identifier. Keep Telegram formatting disabled so monitor details cannot alter message markup.

Down webhook JSON body:

```json
{
  "chat_id": "<TELEGRAM_CHANNEL_ID>",
  "text": "MarketEye production freshness DOWN\nMonitor: *monitorFriendlyName*\nURL: *monitorURL*\nDetails: *alertDetails*\nStarted: *alertDateTime*\nInspect /freshness and cron logs. Recovery is manual via GitHub Actions workflow_dispatch.",
  "disable_web_page_preview": true
}
```

Up webhook JSON body:

```json
{
  "chat_id": "<TELEGRAM_CHANNEL_ID>",
  "text": "MarketEye production freshness UP\nMonitor: *monitorFriendlyName*\nURL: *monitorURL*\nRecovered: *alertDateTime*\nDown duration: *alertDuration*",
  "disable_web_page_preview": true
}
```

UptimeRobot replaces the `*...*` alert variables when delivering each webhook. Confirm the rendered down and up messages in the existing alerts channel before enabling the monitor.

### Delivery limitation and fallback

UptimeRobot custom webhook delivery is **single-attempt**: it does not provide an at-least-once retry guarantee. A Telegram outage, transient network error, or expired bot credential can therefore lose the only down or up notification. The monitor state and `/freshness` remain the source of truth; absence of a Telegram message is not proof that production is fresh.

During a live incident, if an expected alert is missing, inspect UptimeRobot and the live report immediately. Post a manual status note to the existing alerts channel after verifying the report, including the current status and incident start/recovery time. Do not configure a GitHub token in UptimeRobot or compensate with automatic workflow redispatch.

## Non-destructive webhook tests

Keep the production monitor paused while testing. Use UptimeRobot's alert-contact **Test** action for the down contact and then the up contact. Verify that each action produces exactly one correctly rendered message in the existing alerts channel and that no GitHub Actions run is created. These tests must not stop the API, alter published data, or make `/freshness` artificially stale.

If the installed UptimeRobot UI cannot generate both alert types from the alert-contact test action, use a separate disposable monitor against an operator-controlled test endpoint with the two test alert contacts and a short test-only delay. Drive that disposable endpoint down and up, verify both deliveries, then pause and delete the disposable monitor. Never use the production API or production data as the test switch. Reattach the verified contacts to the production monitor with its required five-minute interval and 60-minute delay.

Because delivery is single-attempt, repeat a test only after checking UptimeRobot's delivery result and Telegram; avoid interpreting a duplicate manual test as monitor retry behavior.

## Live verification and cache comparison

After enabling the monitor:

1. Request `/freshness` directly and compare its `checked_at`, expected sessions, component statuses, and HTTP headers with UptimeRobot's latest result.
2. Confirm repeated direct requests may reuse the server report for at most 60 seconds, while every response still has `Cache-Control: no-store`.
3. Inspect the first workflow run for each new requirements key (cache miss) and a later matching run (cache hit). Both setup paths must finish `pip check` successfully. Record setup durations and cache keys using the performance handoff.
4. Confirm scheduled slots appear at `:07`/`:37`, the dense overnight window and `03:07` remain, the probe still gates ingest, `workflow_dispatch` still accepts `target_date`, and concurrency still uses `cancel-in-progress: false`.
5. Compare attempted `prune`, `ingest`, `track`, and `publish` timings and US/TO totals with the incident baseline. Preserve retries, failure recording, and publish gates when interpreting a shorter run.

## Manual recovery

For a down alert or an observed non-200 report:

1. Save the report and identify which markets/components are `stale` or `unavailable`. Check `expected_session` and `latest_session`; do not infer holidays from a weekday calendar.
2. Inspect recent workflow runs and the failing run log:

   ```bash
   gh run list --workflow cronjob.yml --limit 10
   gh run view RUN_ID --log
   ```

3. Distinguish provider unavailability from missing/invalid archive artifacts. Check the recorded phase errors and timings; retain the existing probe and publish gates during diagnosis.
4. Recover manually through the existing GitHub workflow when appropriate. A no-argument dispatch retains the probe gate; an explicit target forces the existing backfill path:

   ```bash
   gh workflow run cronjob.yml
   gh workflow run cronjob.yml -f target_date=YYYY-MM-DD
   ```

   Do not add another scheduler, invoke ingest from UptimeRobot, or place a GitHub credential in a webhook.
5. Watch the run to completion, inspect `/freshness`, and wait for UptimeRobot's up transition. If the up webhook is lost, use the manual alert-verification fallback above.

## Next-trading-session validation

After the next provider-completed trading session publishes:

- US and TO `expected_session` match the provider's latest completed sessions rather than calendar yesterday.
- US analytics, StockBounce v1, and StockBounce v2 are fresh with matching latest sessions; TO analytics is fresh.
- Desktop US/TO latest views and both StockBounce versions show the newly published session with no blank Frequencies regression.
- The workflow log contains all attempted phase timings for each processed market/date and preserves any expected skip/retry/failure behavior.
- Probe and ingest dependency caches hit when their full keys match, and `pip check` remains green.
- UptimeRobot remains up without a continuous 60-minute non-200 period, and no manual redispatch is needed once the archive is fresh.

Record the run ID, live report time, cache comparison, and any follow-up in the operational handoff. Scheduling offsets reduce avoidable queue contention but cannot guarantee GitHub scheduler delivery; independent freshness monitoring remains the detection boundary.
