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


def test_polygon_us_cache_hit_skips_http(monkeypatch, postgres_pool):
    del postgres_pool
    monkeypatch.delenv("OHLCV_CACHE_DISABLED", raising=False)
    import core.settings as settings_module

    monkeypatch.setattr(settings_module, "OHLCV_CACHE_DISABLED", False)

    from datetime import date, timedelta

    from db.crud.ohlcv_bars import BarRow, upsert_bars

    end = date.fromisoformat(FIXTURE_DATE)
    start = end - timedelta(days=85)
    rows = [
        BarRow(
            session_date=start + timedelta(days=offset),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1_000_000,
        )
        for offset in range(60)
    ]
    upsert_bars("US", "AAPL", rows)

    calls = {"http": 0}

    def fail_http(self, url, *args, **kwargs):
        del self, url, args, kwargs
        calls["http"] += 1
        raise AssertionError("HTTP should not be called on cache hit")

    monkeypatch.setattr("providers.polygon_us.PolygonUSProvider._http_get", fail_http)

    provider = PolygonUSProvider()
    df = provider.fetch_ohlcv("AAPL", FIXTURE_DATE, offset_n_days=85, actual_offset_n_days=50)
    assert not df.empty
    assert len(df) >= 50
    assert calls["http"] == 0
