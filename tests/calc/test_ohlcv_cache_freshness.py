"""OHLCV PG cache must not serve windows missing the requested session date."""

from datetime import date, timedelta

import pandas as pd

from db.crud.ohlcv_bars import BarRow
from providers.polygon_us import PolygonUSProvider


class _CacheHitProvider(PolygonUSProvider):
    def _fetch_ohlcv_from_api(self, ticker, date, offset_n_days, actual_offset_n_days, utc_dates):
        raise AssertionError("API should run when cache lacks requested session date")


def test_load_ohlcv_window_refetches_when_cache_stops_before_end_date(monkeypatch):
    provider = _CacheHitProvider()
    start = date.fromisoformat("2026-04-30")
    stale_bars = [
        BarRow(
            session_date=start + timedelta(days=i),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=100,
        )
        for i in range(50)
    ]
    assert stale_bars[-1].session_date.isoformat() == "2026-06-18"

    monkeypatch.setattr(
        "providers.ohlcv_cache_mixin.fetch_bars",
        lambda market, ticker, start, end: stale_bars,
    )

    api_df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-06-18", "2026-06-19"], utc=True),
            "open": [1.0, 2.0],
            "high": [1.0, 2.0],
            "low": [1.0, 2.0],
            "close": [1.0, 2.0],
            "volume": [100, 200],
            "ticker": ["SPY", "SPY"],
        }
    )
    monkeypatch.setattr(provider, "_fetch_ohlcv_from_api", lambda *args, **kwargs: api_df)

    df = provider._load_ohlcv_window(
        "SPY", "2026-06-19", offset_n_days=85, actual_offset_n_days=2, utc_dates=True
    )
    assert not df.empty
    assert df.sort_values("date")["date"].iloc[-1].strftime("%Y-%m-%d") == "2026-06-19"
