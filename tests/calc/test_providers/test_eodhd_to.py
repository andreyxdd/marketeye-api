import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from providers.eodhd_to import EodhdTOProvider
from tests.helpers.constants import FIXTURE_DATE

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "golden"
OHLCV_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "ohlcv"


def _eodhd_rows(n: int = 55):
    rows = []
    for i in range(n):
        rows.append(
            {
                "date": f"2024-0{(4 - i // 30) if i < 90 else 1}-{(i % 28) + 1:02d}",
                "open": 100 + i,
                "high": 101 + i,
                "low": 99 + i,
                "close": 100.5 + i,
                "volume": 1_000_000 + i,
            }
        )
    return rows


@pytest.fixture
def eodhd_to_provider():
    return EodhdTOProvider()


def test_eodhd_to_fetch_ohlcv(eodhd_to_provider, monkeypatch):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = _eodhd_rows()
    monkeypatch.setattr("providers.eodhd_to.requests.get", lambda *a, **k: response)

    df = eodhd_to_provider.fetch_ohlcv("SHOP", FIXTURE_DATE, offset_n_days=85, actual_offset_n_days=50)
    assert not df.empty
    assert df.iloc[0]["ticker"] == "SHOP"


def test_eodhd_to_fetch_ticker_analytics(eodhd_to_provider, monkeypatch):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = _eodhd_rows()
    monkeypatch.setattr("providers.eodhd_to.requests.get", lambda *a, **k: response)

    analytics = eodhd_to_provider.fetch_ticker_analytics("SHOP", FIXTURE_DATE)
    assert analytics
    assert analytics["ticker"] == "SHOP"
    assert "mfi" in analytics


def test_eodhd_to_fetch_ticker_universe(eodhd_to_provider, monkeypatch):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = [
        {"Code": "SHOP", "Type": "Common Stock"},
        {"Code": "RY", "Type": "Common Stock"},
        {"Code": "XYZ", "Type": "ETF"},
    ]
    monkeypatch.setattr("providers.eodhd_to.requests.get", lambda *a, **k: response)

    tickers = eodhd_to_provider.fetch_ticker_universe(FIXTURE_DATE)
    assert tickers == ["SHOP", "RY"]
