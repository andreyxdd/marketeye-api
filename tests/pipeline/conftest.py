"""Isolated Mongo state for pipeline integration tests."""

import pytest
import pytest_asyncio

from core.settings import MONGO_DB_NAME
from db.crud.analytics import MONGO_COLLECTION_NAME
from tests.helpers.constants import CALC_TICKERS, PIPELINE_TICKERS
from tests.helpers.seed import seed_support_collections

OHLCV_DIR = __import__("pathlib").Path(__file__).resolve().parents[1] / "fixtures" / "ohlcv"


@pytest_asyncio.fixture
async def pipeline_db(mongo_client):
    await mongo_client[MONGO_DB_NAME][MONGO_COLLECTION_NAME].delete_many({})
    if await mongo_client[MONGO_DB_NAME]["scrapes"].count_documents({}) == 0:
        await seed_support_collections(mongo_client)
    yield mongo_client


@pytest.fixture(autouse=True)
def mock_polygon(monkeypatch):
    import json

    import requests

    monkeypatch.setattr(
        "db.crud.analytics.get_polygon_tickers",
        lambda date: list(PIPELINE_TICKERS),
    )

    def fake_get(url, *args, **kwargs):
        for ticker in CALC_TICKERS:
            if f"/ticker/{ticker.upper()}/" in url:
                payload = json.loads((OHLCV_DIR / f"{ticker}.json").read_text())
                response = requests.Response()
                response.status_code = 200
                response._content = json.dumps(payload).encode("utf-8")
                return response
        raise AssertionError(f"unexpected polygon URL: {url}")

    monkeypatch.setattr("utils.handle_external_apis.requests.get", fake_get)
