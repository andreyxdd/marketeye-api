"""Resolve LastCompletedSession and PriorCompletedSession from OHLCV bars."""

from typing import Optional, Tuple

import pandas as pd

from utils.handle_datetimes import get_date_string


def session_dates_from_ohlcv(df: pd.DataFrame) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (last_completed_session, prior_completed_session) as YYYY-MM-DD strings.

    Uses the two most recent distinct bar dates in the frame (sorted ascending).
    """
    if df is None or df.empty or "date" not in df.columns:
        return None, None

    normalized = df.sort_values("date")["date"].drop_duplicates()
    if normalized.empty:
        return None, None

    def _as_date_string(value) -> str:
        if isinstance(value, str):
            return value[:10]
        return get_date_string(value)

    unique_dates = [_as_date_string(value) for value in normalized.tolist()]
    last_session = unique_dates[-1]
    prior_session = unique_dates[-2] if len(unique_dates) >= 2 else None
    return last_session, prior_session
