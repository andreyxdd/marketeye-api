# Continue — marketeye-api client test suite

## Last action

v1 plan complete: **34 pytest tests green** on `main`; real Polygon OHLCV (83 bars) committed in `01613e3`. Handoff doc: `docs/handoff/client-api-e2e-tests.md`.

## Next action

Start **AnalyticsService extraction** (plan Phase 1 refactor):

1. Read `api/endpoints/analytics.py` + `db/crud/analytics.py`.
2. Introduce `services/analytics_service.py` with methods matching the 6 client routes.
3. Keep route handlers thin; run `pytest tests/e2e -v` after each endpoint moved.

## Why

Tier A/B/C/B′ guard US behavior; provider shell exists (`providers/polygon_us.py`) but routes still mix HTTP, CRUD, and external calls. Refactor is the plan’s stated follow-on while tests stay local-only.

## Open threads

- `market=` param + non-US — Phase 2, product-dependent.
- GHA e2e workflow — deferred until refactor settles.
- Prod CVI aggregation may still edge-case on flat markets (`get_slope_normalized` div-by-zero) — not hit with current fixtures.

## Do not

- Remove conftest local mongo/redis overrides.
- Re-add CVI stub in `tests/e2e/conftest.py`.
- Run capture without `.env` `POLYGON_API_KEY` expecting real bars (falls back to synthetic / existing).
