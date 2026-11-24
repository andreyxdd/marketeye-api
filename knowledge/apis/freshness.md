---
type: api
name: Production freshness API
status: accepted
---

# Production freshness API

## Scope and callers

`GET /freshness` is an operational read endpoint for the external UptimeRobot monitor and developers. It answers whether the PostgreSQL serving archive contains valid artifacts for the latest completed session reported by each market's provider. It does not serve desktop ticker data and does not replace `/healthz` or `/readyz`.

The monitored components are US analytics, TO analytics, US StockBounce v1, and US StockBounce v2. Analytics freshness follows the same archive-completeness semantics used by the cron probe. StockBounce snapshots must pass their existing v1/v2 validators and match the expected session date.

## Endpoint

| Method | Path | Request | Success | Errors |
|--------|------|---------|---------|--------|
| GET | `/freshness` | No query or body | 200 with a fresh report | 503 with a stale or unavailable report and `Retry-After: 300` |

There is no pagination because the response is one fixed-size aggregate. The route is unversioned like the other operational health routes; changes must be additive. Any incompatible future contract requires a new versioned route rather than changing existing field meanings.

### Response shape

Both 200 and 503 use the same report shape so monitor incidents remain diagnosable:

```json
{
  "status": "fresh",
  "checked_at": "2026-11-24T06:16:28Z",
  "markets": {
    "US": {
      "expected_session": "2026-11-23",
      "components": {
        "analytics": {"status": "fresh", "latest_session": "2026-11-23"},
        "stock_bounce_v1": {"status": "fresh", "latest_session": "2026-11-23"},
        "stock_bounce_v2": {"status": "fresh", "latest_session": "2026-11-23"}
      }
    },
    "TO": {
      "expected_session": "2026-11-23",
      "components": {
        "analytics": {"status": "fresh", "latest_session": "2026-11-23"}
      }
    }
  }
}
```

`status` is `fresh` only when every component is fresh. It is `stale` when at least one expected artifact is absent, invalid, or older than the provider's latest completed session. It is `unavailable` when a provider or required archive lookup cannot produce a trustworthy answer. A component can be `stale` or `unavailable`; its `latest_session` is the newest archived session for that component, or `null` when none exists or cannot be determined.

`checked_at` is the UTC report-generation time. No stack traces, provider responses, query text, ticker rows, credentials, or credential-bearing URLs appear in the report.

## Auth and disclosure

The endpoint is intentionally public, like `/healthz` and `/readyz`, and requires no API key. Its fixed-size response contains only operational statuses and market session dates. This avoids placing the desktop API key or a new monitoring credential in UptimeRobot.

## Status codes and headers

- `200`: all components are fresh.
- `503`: any component is stale or unavailable. Include `Retry-After: 300`.
- All responses include `Cache-Control: no-store` so UptimeRobot and intermediaries do not reuse an old report.

The endpoint does not return 200 with an error payload. Unexpected internal details are logged server-side but not exposed.

## Idempotency, caching, and consistency

GET is read-only and retry-safe; no ingestion, repair, or notification is triggered by a read. Provider probes run off the event loop and are bounded. A 60-second server-side cache limits provider/API load from repeated external requests. A cached report may therefore lag current publication by at most 60 seconds, which is within the external monitor's five-minute interval and 60-minute alert grace.

The report is eventually consistent with provider publication and cron writes. It does not infer market holidays from a weekday calendar: expected sessions come from the same provider resolution used by the cron. A provider that has not yet published a new bar leaves the prior completed session as expected.

## External monitoring and recovery

UptimeRobot checks the endpoint every five minutes and alerts only after 60 minutes of continuous non-200 responses. Down and up webhooks call the Telegram Bot API directly using the existing dev bot and alerts channel. The bot token is stored only in UptimeRobot's protected webhook configuration.

Recovery remains manual: inspect the report and cron logs, then use the existing `workflow_dispatch` when appropriate. The monitor never triggers ingestion automatically and stores no GitHub credential. UptimeRobot webhook delivery is single-attempt and requires a plan supporting custom webhooks; the operations runbook must include a down/up delivery test and a manual alert-verification fallback.
