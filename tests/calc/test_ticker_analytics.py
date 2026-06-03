import json
from pathlib import Path

import pytest

from tests.helpers.constants import CALC_TICKERS, FIXTURE_DATE
from utils.handle_calculations import compute_base_analytics, compute_extra_analytics
from utils.handle_external_apis import get_ticker_analytics
import pandas as pd

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "golden"
OHLCV_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ohlcv"


def _load_golden(ticker: str) -> dict:
    path = GOLDEN_DIR / f"{ticker.lower()}_{FIXTURE_DATE}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _ohlcv_dataframe(ticker: str) -> pd.DataFrame:
    payload = json.loads((OHLCV_DIR / f"{ticker}.json").read_text(encoding="utf-8"))
    df = pd.DataFrame(payload["results"])
    df["date"] = pd.to_datetime(df["t"], unit="ms").dt.strftime("%Y-%m-%d")
    df = df.rename(
        columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
    )
    df["ticker"] = ticker.upper()
    return df[["ticker", "date", "open", "high", "low", "close", "volume"]]


@pytest.mark.parametrize("ticker", CALC_TICKERS)
def test_get_ticker_analytics_matches_golden(ticker):
    golden = _load_golden(ticker)
    analytics = get_ticker_analytics(ticker, FIXTURE_DATE)
    for field, expected in golden.items():
        assert field in analytics
        assert analytics[field] == pytest.approx(expected, rel=1e-6, abs=1e-6)


def test_compute_base_analytics_last_row_macd():
    df = _ohlcv_dataframe("AAPL")
    base = compute_base_analytics(df)
    golden = _load_golden("AAPL")
    assert base["macd"] == pytest.approx(golden["macd"], rel=1e-6, abs=1e-6)
    assert base["one_day_avg_mf"] == pytest.approx(
        golden["one_day_avg_mf"], rel=1e-6, abs=1e-6
    )


def test_compute_extra_analytics_mfi():
    df = _ohlcv_dataframe("AAPL")
    extra = compute_extra_analytics(df)
    golden = _load_golden("AAPL")
    assert extra["mfi"] == pytest.approx(golden["mfi"], rel=1e-6, abs=1e-6)
