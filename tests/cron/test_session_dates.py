"""Tests for session date resolution from OHLCV bars."""

import json
from pathlib import Path

import pandas as pd
import pytest

from services.session_dates import session_dates_from_ohlcv
from tests.helpers.constants import FIXTURE_DATE

OHLCV_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ohlcv"


def _aapl_ohlcv_dataframe() -> pd.DataFrame:
    payload = json.loads((OHLCV_DIR / "AAPL.json").read_text(encoding="utf-8"))
    df = pd.DataFrame(payload["results"])
    df["date"] = pd.to_datetime(df["t"], unit="ms").dt.strftime("%Y-%m-%d")
    df = df.rename(
        columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
    )
    df["ticker"] = "AAPL"
    return df[["date", "open", "high", "low", "close", "volume", "ticker"]]


def test_session_dates_from_ohlcv_fixture():
    df = _aapl_ohlcv_dataframe()
    last_session, prior_session = session_dates_from_ohlcv(df)

    assert last_session == FIXTURE_DATE
    assert prior_session == "2024-05-31"


def test_session_dates_from_ohlcv_empty():
    assert session_dates_from_ohlcv(pd.DataFrame()) == (None, None)


def test_session_dates_from_ohlcv_single_bar():
    df = pd.DataFrame(
        {
            "date": ["2024-06-03"],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [1],
            "ticker": ["AAPL"],
        }
    )
    last_session, prior_session = session_dates_from_ohlcv(df)
    assert last_session == "2024-06-03"
    assert prior_session is None
