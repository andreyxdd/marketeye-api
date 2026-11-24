# Cron performance handoff

## Incident baseline

The eventual successful ingest after the 2026-11-24 scheduled-run gap is the comparison baseline. These are observed GitHub Actions durations, not targets or guarantees:

| Measurement | Baseline |
|---|---:|
| Dependency setup | approximately 16 minutes |
| US processing | 967.6 seconds |
| TO processing | 374.19 seconds |

The reliability change offsets scheduled slots and caches the probe and ingest virtual environments. It does not change ingest algorithms. Cache setup and market totals therefore remain separate measurements: a faster cache restore does not imply faster provider fetch or analytics processing.

## Reproducible phase measurements

`cronjob.py` records elapsed seconds for every attempted `prune`, `ingest`, `track`, and `publish` phase, keyed by market and session date. The final cron summary prints these values after the per-market totals. A failed phase still emits its timing; a publish timing includes the existing single retry for transient connection errors. Phases that are not attempted do not emit a timing.

Use the existing GitHub Actions workflow for comparisons; no additional ingestion runner is required:

```bash
# Select the cache-miss run after deployment and a later cache-hit run.
gh run list --workflow cronjob.yml --limit 10

# Save each completed run without truncating its output.
gh run view RUN_ID --log > /tmp/marketeye-cron-RUN_ID.log

# Extract setup, phase, and market measurements for side-by-side comparison.
rg "Set up cache|Install probe dependencies|Install Python dependencies|pip check|Phase timings|\[prune\]|\[ingest\]|\[track\]|\[publish\]|Per-market summary|Market US total|Market TO total" /tmp/marketeye-cron-RUN_ID.log
```

For each comparison, record:

1. Run ID, trigger, commit SHA, target date (if any), and whether the run needed ingest.
2. Probe and ingest cache keys and cache-hit results. A no-work run exercises only the probe cache and must not be treated as an ingest cache-hit benchmark.
3. Dependency setup duration for cache miss versus cache hit, including `pip check` in both paths.
4. Every attempted phase timing and the US/TO totals. Compare like-for-like market/session work rather than only total workflow wall time.
5. Provider failures, retries, skipped publish gates, and partial failures alongside the durations so a shorter failed run is not mistaken for an improvement.

The first production run with a new requirements hash is a cache miss. Later runs with the same OS, architecture, Python version, and requirements hash should restore that environment. A restore fallback still requires successful installation and `pip check`; it never waives dependency integrity validation.
