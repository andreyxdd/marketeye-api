"""EodhdUSProvider unit tests."""

from unittest.mock import MagicMock

import pytest

from providers.eodhd_us import EodhdUSProvider
from tests.helpers.constants import FIXTURE_DATE


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
def eodhd_us_provider():
    return EodhdUSProvider()


def test_eodhd_us_symbol_suffix(eodhd_us_provider):
    assert eodhd_us_provider._eod_symbol("aapl") == "AAPL.US"


def test_eodhd_us_fetch_ohlcv(eodhd_us_provider, monkeypatch):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = _eodhd_rows()
    monkeypatch.setattr(
        "providers.eodhd_us.EodhdUSProvider._http_get", lambda *a, **k: response
    )

    df = eodhd_us_provider.fetch_ohlcv(
        "AAPL", FIXTURE_DATE, offset_n_days=85, actual_offset_n_days=50
    )
    assert not df.empty
    assert df.iloc[0]["ticker"] == "AAPL"


def test_eodhd_us_fetch_ticker_universe_nyse_nasdaq(eodhd_us_provider, monkeypatch):
    responses = {
        "NYSE": [
            {"Code": "IBM", "Type": "Common Stock"},
            {"Code": "SPY", "Type": "ETF"},
        ],
        "NASDAQ": [
            {"Code": "AAPL", "Type": "Common Stock"},
            {"Code": "QQQ", "Type": "ETF"},
        ],
    }

    def fake_http_get(self, url, **kwargs):
        del self, kwargs
        response = MagicMock()
        response.status_code = 200
        for exchange, payload in responses.items():
            if f"/exchange-symbol-list/{exchange}" in url:
                response.json.return_value = payload
                return response
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(
        "providers.eodhd_us.EodhdUSProvider._http_get", fake_http_get
    )

    tickers = eodhd_us_provider.fetch_ticker_universe(FIXTURE_DATE)
    assert tickers == ["IBM", "AAPL"]


def test_eodhd_us_probe_ticker_is_spy(eodhd_us_provider):
    assert eodhd_us_provider.probe_ticker == "SPY"
    assert eodhd_us_provider.market == "US"
