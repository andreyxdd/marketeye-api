"""Isolated Mongo state for pipeline integration tests."""

import pytest
import pytest_asyncio

from core.settings import MONGO_DB_NAME
from db.crud.analytics import MONGO_COLLECTION_NAME
from tests.helpers.constants import CALC_TICKERS, PIPELINE_TICKERS
from tests.helpers.seed import seed_support_collections

OHLCV_DIR = __import__("pathlib").Path(__file__).resolve().parents[1] / "fixtures" / "ohlcv"


class _StubUSProvider:
    market = "US"

    def fetch_ticker_universe(self, date):
        del date
        return list(PIPELINE_TICKERS)

    def fetch_ticker_base_analytics(self, ticker, date, offset_n_days=85, actual_offset_n_days=50):
        import json
        import requests
        from providers.polygon_us import POLYGON_SYMBOL_ALIASES
        from providers.analytics_mixin import base_analytics_from_ohlcv_utc
        import pandas as pd

        polygon_symbol = POLYGON_SYMBOL_ALIASES.get(ticker.upper(), ticker.upper())
        payload = json.loads((OHLCV_DIR / f"{ticker}.json").read_text())
        results = payload["results"]
        df = pd.DataFrame(results)
        df["t"] = pd.to_datetime(df["t"], unit="ms", utc=True)
        df = df.rename(
            columns={
                "t": "date",
                "o": "open",
                "h": "high",
                "l": "low",
                "c": "close",
                "v": "volume",
            }
        )
        df = df[["date", "open", "high", "low", "close", "volume"]]
        df["ticker"] = ticker.upper()
        analytics = base_analytics_from_ohlcv_utc(df)
        if analytics:
            analytics["market"] = "US"
        return analytics

    def fetch_ticker_extra_analytics(self, ticker, date, offset_n_days=85, actual_offset_n_days=50):
        del ticker, date, offset_n_days, actual_offset_n_days
        return {}


@pytest_asyncio.fixture
async def pipeline_db(mongo_client):
    await mongo_client[MONGO_DB_NAME][MONGO_COLLECTION_NAME].delete_many({})
    if await mongo_client[MONGO_DB_NAME]["scrapes"].count_documents({}) == 0:
        await seed_support_collections(mongo_client)
    yield mongo_client


@pytest.fixture(autouse=True)
def mock_provider_registry(monkeypatch):
    stub = _StubUSProvider()

    def _get_provider(market="US"):
        del market
        return stub

    monkeypatch.setattr("providers.get_market_data_provider", _get_provider)
    monkeypatch.setattr(
        "utils.handle_external_apis.get_market_data_provider", _get_provider
    )

    import json
    import requests
    from providers.polygon_us import POLYGON_SYMBOL_ALIASES

    def fake_http_get(self, url, *args, **kwargs):
        del self, args, kwargs
        for ticker in CALC_TICKERS:
            polygon_symbol = POLYGON_SYMBOL_ALIASES.get(ticker.upper(), ticker.upper())
            if f"/ticker/{polygon_symbol}/" in url or f"/ticker/{ticker.upper()}/" in url:
                payload = json.loads((OHLCV_DIR / f"{ticker}.json").read_text())
                response = requests.Response()
                response.status_code = 200
                response._content = json.dumps(payload).encode("utf-8")
                return response
        raise AssertionError(f"unexpected polygon URL: {url}")

    monkeypatch.setattr("providers.polygon_us.PolygonUSProvider._http_get", fake_http_get)
    monkeypatch.setattr(
        "services.analytics_service.external_get_ticker_extra_analytics",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        "services.analytics_service.get_quarterly_free_cash_flow_polygon",
        lambda *args, **kwargs: "N/A",
    )
