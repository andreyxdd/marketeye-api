"""Shared analytics helpers for market data providers."""

from typing import Optional

import pandas as pd

from utils.handle_calculations import compute_base_analytics, compute_extra_analytics


def analytics_from_ohlcv(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    return {
        **compute_base_analytics(df),
        **compute_extra_analytics(df),
    }


def base_analytics_from_ohlcv_utc(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    return compute_base_analytics(df)


def extra_analytics_from_ohlcv(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    return compute_extra_analytics(df)
