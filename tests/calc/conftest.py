"""EODHD HTTP mocking for US calculation tests."""

import json
from pathlib import Path

import pytest
import requests

from tests.helpers.constants import CALC_TICKERS

OHLCV_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ohlcv"


@pytest.fixture(autouse=True)
def mock_eodhd_us_requests(monkeypatch):
    def fake_http_get(self, url, *args, **kwargs):
        del self, args, kwargs
        for ticker in CALC_TICKERS:
            if f"/eod/{ticker.upper()}.US" in url:
                payload = json.loads((OHLCV_DIR / f"{ticker}.json").read_text())
                response = requests.Response()
                response.status_code = 200
                response._content = json.dumps(payload).encode("utf-8")
                return response
        raise AssertionError(f"unexpected eodhd URL: {url}")

    monkeypatch.setattr("providers.eodhd_us.EodhdUSProvider._http_get", fake_http_get)
