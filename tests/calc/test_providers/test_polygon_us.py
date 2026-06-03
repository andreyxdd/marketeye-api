import json
from pathlib import Path

import pytest

from providers.polygon_us import PolygonUSProvider
from tests.helpers.constants import CALC_TICKERS, FIXTURE_DATE

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "golden"
OHLCV_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "ohlcv"


def _load_golden(ticker: str) -> dict:
    path = GOLDEN_DIR / f"{ticker.lower()}_{FIXTURE_DATE}.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def polygon_us_provider():
    return PolygonUSProvider()


@pytest.mark.parametrize("ticker", CALC_TICKERS)
def test_polygon_us_provider_matches_golden(ticker, polygon_us_provider, mock_polygon_requests):
    del mock_polygon_requests
    golden = _load_golden(ticker)
    analytics = polygon_us_provider.fetch_ticker_analytics(ticker, FIXTURE_DATE)
    for field, expected in golden.items():
        assert field in analytics
        assert analytics[field] == pytest.approx(expected, rel=1e-6, abs=1e-6)


def test_polygon_us_fetch_ohlcv_from_fixtures(polygon_us_provider, mock_polygon_requests):
    del mock_polygon_requests
    df = polygon_us_provider.fetch_ohlcv("AAPL", FIXTURE_DATE, offset_n_days=85, actual_offset_n_days=50)
    assert not df.empty
    payload = json.loads((OHLCV_DIR / "AAPL.json").read_text(encoding="utf-8"))
    assert len(df) >= 50
    assert len(df) == len(payload["results"])
