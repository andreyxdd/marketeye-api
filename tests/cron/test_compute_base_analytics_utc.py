"""UTC OHLCV path used by cron fetch_ohlcv_utc must compute without date errors."""

import numpy as np
import pandas as pd
import pytest

from utils.handle_calculations import compute_base_analytics
from utils.handle_datetimes import bar_date_to_epoch_ms, bar_date_to_string, get_epoch


def _utc_ohlcv_frame(ticker: str = "HOT-U", rows: int = 55) -> pd.DataFrame:
    dates = pd.to_datetime(
        [1781568000000 + i * 86_400_000 for i in range(rows)],
        unit="ms",
        utc=True,
    )
    return pd.DataFrame(
        {
            "date": dates,
            "open": np.linspace(10, 12, rows),
            "high": np.linspace(11, 13, rows),
            "low": np.linspace(9, 11, rows),
            "close": np.linspace(10.5, 12.5, rows),
            "volume": np.linspace(1000, 2000, rows),
            "ticker": ticker,
        }
    )


def test_compute_base_analytics_utc_timestamps():
    df = _utc_ohlcv_frame()
    result = compute_base_analytics(df)
    assert result["ticker"] == "HOT-U"
    assert isinstance(result["date"], float)
    assert bar_date_to_string(result["date"]) == bar_date_to_string(df["date"].iloc[-1])
    assert len(result["bounce"]) == 18


def test_compute_base_analytics_string_dates():
    df = _utc_ohlcv_frame()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    result = compute_base_analytics(df)
    assert bar_date_to_string(result["date"]) == df["date"].iloc[-1]


@pytest.mark.parametrize("epoch_value", [1781654400000, 1781654400000.0, np.float64(1781654400000.0)])
def test_bar_date_to_string_accepts_numpy_epoch(epoch_value):
    assert bar_date_to_string(epoch_value) == "2026-06-17"
    assert get_epoch("2026-06-17") == float(epoch_value)


def test_bar_date_to_epoch_ms_normalizes_polygon_session_timestamp():
    ts = pd.Timestamp("2026-06-18 04:00:00", tz="UTC")
    assert bar_date_to_epoch_ms(ts) == get_epoch("2026-06-18")
    assert bar_date_to_epoch_ms(ts) != ts.value / 1_000_000


def test_compute_base_analytics_stores_canonical_epoch():
    df = _utc_ohlcv_frame()
    last_bar = df["date"].iloc[-1]
    result = compute_base_analytics(df)
    assert result["date"] == get_epoch(bar_date_to_string(last_bar))
