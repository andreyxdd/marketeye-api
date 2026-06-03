# Local test suite

Run MongoDB and Redis, generate fixtures once, then pytest.

```bash
docker compose -f docker-compose.test.yml up -d

export MONGO_URI=mongodb://localhost:27017
export REDIS_URI=redis://localhost:6379/1
export API_KEY=test-api-key-e2e
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

## OHLCV capture

`scripts/capture_ohlcv_fixtures.py --market US` uses `POLYGON_API_KEY` when set; otherwise synthetic bars. Re-run after changing calc paths to refresh `tests/fixtures/ohlcv/` and `tests/fixtures/golden/`.
