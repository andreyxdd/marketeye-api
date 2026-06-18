"""Sync CRUD for normalized OHLCV bars (provider write-through cache)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from typing import Optional

from db.ohlcv_sync import get_ohlcv_sync_pool


@dataclass(frozen=True)
class BarRow:
    session_date: date_type
    open: float
    high: float
    low: float
    close: float
    volume: int


def _to_date(value) -> date_type:
    if isinstance(value, date_type):
        return value
    return date_type.fromisoformat(str(value))


def fetch_bars(
    market: str,
    ticker: str,
    start_date,
    end_date,
) -> list[BarRow]:
    """Return bars in [start_date, end_date]; empty list on error."""
    try:
        pool = get_ohlcv_sync_pool()
        if pool is None:
            return []
        start = _to_date(start_date)
        end = _to_date(end_date)
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT session_date, open, high, low, close, volume
                    FROM ohlcv_bars
                    WHERE market = %s
                      AND ticker = %s
                      AND session_date >= %s
                      AND session_date <= %s
                    ORDER BY session_date DESC
                    """,
                    (market, ticker, start, end),
                )
                rows = cur.fetchall()
        return [
            BarRow(
                session_date=row[0],
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=int(row[5]),
            )
            for row in rows
        ]
    except Exception as exc:  # pylint: disable=broad-except
        print(f"db/crud/ohlcv_bars.py fetch_bars: {exc}")
        return []


def upsert_bars(market: str, ticker: str, rows: list[BarRow]) -> None:
    """Batch upsert bars; no-op on error."""
    if not rows:
        return
    try:
        pool = get_ohlcv_sync_pool()
        if pool is None:
            return
        values = [
            (
                market,
                ticker,
                row.session_date,
                row.open,
                row.high,
                row.low,
                row.close,
                row.volume,
            )
            for row in rows
        ]
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO ohlcv_bars (
                        market, ticker, session_date,
                        open, high, low, close, volume
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (market, ticker, session_date)
                    DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        fetched_at = NOW()
                    """,
                    values,
                )
            conn.commit()
    except Exception as exc:  # pylint: disable=broad-except
        print(f"db/crud/ohlcv_bars.py upsert_bars: {exc}")


def delete_bars_for_session_date(session_date) -> int:
    """Delete all bars for one session_date; return 0 on error."""
    try:
        pool = get_ohlcv_sync_pool()
        if pool is None:
            return 0
        target = _to_date(session_date)
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM ohlcv_bars WHERE session_date = %s",
                    (target,),
                )
                deleted = cur.rowcount
            conn.commit()
        return deleted
    except Exception as exc:  # pylint: disable=broad-except
        print(f"db/crud/ohlcv_bars.py delete_bars_for_session_date: {exc}")
        return 0


def oldest_session_date() -> Optional[date_type]:
    """Return globally oldest session_date in ohlcv_bars; None on empty/error."""
    try:
        pool = get_ohlcv_sync_pool()
        if pool is None:
            return None
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT MIN(session_date) FROM ohlcv_bars")
                row = cur.fetchone()
        if row is None or row[0] is None:
            return None
        return row[0]
    except Exception as exc:  # pylint: disable=broad-except
        print(f"db/crud/ohlcv_bars.py oldest_session_date: {exc}")
        return None
