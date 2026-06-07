# Handoff — Client API local test suite (v1 complete)

**Date:** 2026-06-03  
**Branch:** `main` (local; not pushed in this session)  
**Plan:** `.cursor/plans/client_api_e2e_tests_eddeecd0.plan.md`  
**Status:** v1 deliverables **done**. Phase 2 / refactor **not started**.

---

## Last verified state

```bash
docker compose -f docker-compose.test.yml up -d
source .venv/bin/activate   # Python 3.12+; pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -v
# → 34 passed
```

Latest commit: `01613e3` — real Polygon OHLCV + golden fixtures (83 bars × AAPL/MSFT/GOOG @ `2024-06-03`).

---

## What shipped

| Area | Location | Notes |
|------|----------|--------|
| **Tier A** HTTP e2e | `tests/e2e/` | 6 client routes + auth/422; **real CVI** from Mongo agg |
| **Tier B** calc golden | `tests/calc/` | OHLCV → `compute_*`; mocks Polygon HTTP only |
| **Tier B′** provider | `tests/calc/test_providers/` | `PolygonUSProvider` vs same goldens |
| **Tier C** pipeline | `tests/pipeline/` | insert → `get_analytics_sorted_by` |
| **Fixtures** | `tests/fixtures/{mongo,external,ohlcv,golden}/` | Anchor **`2024-06-03`**, 50 US tickers in Mongo seed |
| **Provider (Phase 2 seed)** | `providers/` | `MarketDataProvider` protocol + `PolygonUSProvider`; `GOOG` → `GOOGL` on Polygon |
| **Infra** | `docker-compose.test.yml`, `pytest.ini`, `requirements-dev.txt` | Local mongo:6 + redis:7 |
| **Docs** | `tests/README.md`, `CONTEXT.md` | Glossary + runbook |
| **Prod fixes** | `db/crud/analytics.py`, `api/endpoints/analytics.py`, `core/settings.py`, pandas `QE` | Needed for tests to pass |

### Commit stack (newest first)

```
01613e3 test: refresh OHLCV and golden fixtures from Polygon
dd714d2 test: load secrets from .env for local pytest and capture
a55f8b5 test: add Tier B′ provider goldens and plan glossary docs
543d9d1 feat(providers): extract PolygonUSProvider for US market data
73cc441 fix(analytics): real CVI aggregation from Mongo seed
db35c2b test: add local pytest suite for client API routes
8d03ec3 fix: support local test DB and harden analytics paths
```

---

## Environment model

| Variable | Source in tests | Value / behavior |
|----------|-----------------|------------------|
| `POLYGON_API_KEY`, `QUANDL_*`, etc. | Repo-root **`.env`** (`load_dotenv(..., override=True)`) | Real secrets for capture; not committed |
| `MONGO_URI`, `REDIS_URI`, `MONGO_DB_NAME` | **Forced** in `tests/conftest.py` | `localhost:27017`, `redis://localhost:6379/1`, `marketeye_test` |
| `API_KEY` | **Forced** in `tests/conftest.py` | `test-api-key-e2e` (not prod key from `.env`) |

**Important:** `tests/conftest.py` must set local mongo/redis **before** importing `db.*` (settings loads on import).

### Refresh OHLCV / goldens

```bash
python scripts/capture_ohlcv_fixtures.py --market US
pytest tests/calc tests/pipeline -v
```

- Reads `POLYGON_API_KEY` from `.env`.
- Requires **≥50 bars** per ticker or keeps existing fixture / synthetic fallback.
- Polygon can return transient 500s; script retries (AAPL often needs 2–3 attempts).
- `GOOG` fetched as `GOOGL` on Polygon; saved as `GOOG.json`.

### Regenerate Mongo seed JSON

```bash
python tests/helpers/generate_fixtures.py
```

Re-seeds on each pytest session via `tests/conftest.py` → `seed_collections`.

---

## Architecture unlocked (not implemented)

Green tests guard these refactors (see plan mermaid):

1. **`AnalyticsService`** — thin FastAPI routes; domain owns sort/list/ticker assembly.
2. **Full provider wiring** — FCF, SP500/VIX still in `utils/handle_external_apis.py` (Tier A stubs them).
3. **Multi-market** — `market=` query param, Tier B′ per exchange, optional Mongo `{ticker, market, date}`.

---

## Explicitly out of scope (v1)

- `.github/workflows/e2e.yml` — local-only during refactor
- Scrapy / bounce routes
- Non-US markets
- `market=` API param + pilot market Tier A

---

## Known gotchas

1. **Polygon flakiness** — 500 / auth errors intermittent; capture script retries; don’t overwrite fixtures with &lt;50 bars.
2. **Motor event loop** — `pytest.ini` uses `asyncio_mode=auto` + session loop scope; e2e clears `app.router.on_startup/shutdown` to avoid wrong-loop Mongo reconnect.
3. **Bound imports** — external stubs patch both `utils.handle_external_apis` **and** `api.endpoints.analytics` / `db.crud.analytics` (see `tests/e2e/conftest.py`).
4. **CVI fixtures** — `generate_fixtures.py` varies advancing ticker count by weekday (`advancing_ticker_count`); flat 25/25 adv/dec breaks slope (NaN).
5. **Dev deps** — need `jinja2`, `python-dotenv` (in `requirements-dev.txt`) for `main` import in e2e tests.
6. **`.env` is gitignored** — never commit; contains prod Mongo/Redis/API credentials.

---

## Suggested next actions (pick one)

### A — Refactor under green tests (recommended)

1. Extract `AnalyticsService` from `api/endpoints/analytics.py`.
2. Move remaining Polygon calls behind `PolygonUSProvider`; keep Tier B goldens byte-identical.
3. Run `pytest tests/ -v` after each slice.

### B — Phase 2 multi-market

1. Add second provider + `tests/calc/test_providers/test_<market>.py`.
2. Generalize `capture_ohlcv_fixtures.py` `MARKET_TICKERS` map.
3. Add `market=` param when product requires it.

### C — CI (when refactor stabilizes)

1. Add `.github/workflows/e2e.yml` with service containers mirroring `docker-compose.test.yml`.
2. Use GitHub secrets for `POLYGON_API_KEY` or keep calc tests on committed fixtures only (no live Polygon in CI).

---

## Key files (quick map)

```
tests/conftest.py              # .env + local infra overrides; session Mongo seed
tests/e2e/conftest.py          # HTTP stubs (not CVI); httpx client
tests/helpers/generate_fixtures.py
scripts/capture_ohlcv_fixtures.py
providers/polygon_us.py
utils/handle_external_apis.py  # delegates OHLCV to provider
db/crud/analytics.py           # CVI agg, insert, sort
```

---

## Do not

- Point pytest at prod Mongo/Redis from `.env` (conftest overrides — don’t remove without replacement).
- Re-stub CVI in Tier A (`get_normalazied_cvi_slope` must stay real).
- Commit `.env` or capture output that embeds API keys in error URLs (script redacts to `***`).
- Assume v1 tests cover non-US or Scrapy pipelines.

---

## Uncommitted / local-only

- `.pi/` memory DB noise — ignore for commits.
- `.venv/` — local; not in repo.
- Branch ahead of `origin/main` — push when ready.
