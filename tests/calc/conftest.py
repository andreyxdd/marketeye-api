"""Polygon HTTP mocking for calculation tests."""

import json
from pathlib import Path

import pytest
import requests

from tests.helpers.constants import CALC_TICKERS

OHLCV_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ohlcv"


@pytest.fixture(autouse=True)
def mock_polygon_requests(monkeypatch):
    def fake_get(url, *args, **kwargs):
        for ticker in CALC_TICKERS:
            if f"/ticker/{ticker.upper()}/" in url:
                payload = json.loads((OHLCV_DIR / f"{ticker}.json").read_text())
                response = requests.Response()
                response.status_code = 200
                response._content = json.dumps(payload).encode("utf-8")
                return response
        raise AssertionError(f"unexpected polygon URL: {url}")

    monkeypatch.setattr("providers.polygon_us.requests.get", fake_get)
