# Local test suite

Run MongoDB and Redis, generate fixtures once, then pytest.

```bash
docker compose -f docker-compose.test.yml up -d

# POLYGON_API_KEY and other secrets: loaded from repo-root `.env`
export MONGO_URI=mongodb://localhost:27017
export REDIS_URI=redis://localhost:6379/1
export MONGO_DB_NAME=marketeye_test

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

python tests/helpers/generate_fixtures.py
python scripts/capture_ohlcv_fixtures.py --market US

pytest tests/ -v
```

## Tiers

| Directory | Purpose |
|-----------|---------|
| `tests/e2e/` | Client HTTP routes (Tier A); real CVI from Mongo |
| `tests/calc/` | Indicator golden tests (Tier B) |
| `tests/calc/test_providers/` | Provider golden tests (Tier B′) |
| `tests/pipeline/` | Insert → sort pipeline (Tier C) |

Anchor date: `2024-06-03`. Local only during architectural refactor.

Glossary: `CONTEXT.md`.

## Environment

Tests load secrets from repo-root `.env` (`POLYGON_API_KEY`, etc.) with `override=True`.
Local Mongo/Redis/API key for the suite are forced in `tests/conftest.py` (docker + `test-api-key-e2e`).

## OHLCV capture

`scripts/capture_ohlcv_fixtures.py --market US` reads `POLYGON_API_KEY` from `.env`.
Requires **≥50 daily bars** per ticker from Polygon; otherwise keeps existing fixtures or synthetic fallback.
Your Polygon plan must include historical aggregates for `2024-06-03` anchor capture to replace committed JSON.
