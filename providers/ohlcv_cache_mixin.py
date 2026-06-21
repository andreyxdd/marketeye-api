"""Write-through PostgreSQL OHLCV cache for market data providers."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from core import settings
from db.crud.ohlcv_bars import BarRow, fetch_bars, upsert_bars


class OhlcvCacheMixin:
    """Mixin: PG-first window load with fail-open HTTP fallback."""

    market: str

    def _normalize_cache_ticker(self, ticker: str) -> str:
        return ticker.upper()

    def _fetch_ohlcv_from_api(
        self,
        ticker: str,
        date: str,
        offset_n_days: int,
        actual_offset_n_days: int,
        utc_dates: bool,
    ) -> pd.DataFrame:
        raise NotImplementedError

    def _bars_to_dataframe(
        self, bars: list[BarRow], ticker: str, utc_dates: bool
    ) -> pd.DataFrame:
        if not bars:
            return pd.DataFrame()
        rows = [
            {
                "date": bar.session_date.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]
        df = pd.DataFrame(rows)
        if utc_dates:
            df["date"] = pd.to_datetime(df["date"], utc=True)
        df["ticker"] = ticker.upper()
        return df

    def _dataframe_to_bar_rows(self, df: pd.DataFrame) -> list[BarRow]:
        if df.empty:
            return []
        rows = []
        for _, row in df.iterrows():
            date_value = row["date"]
            if hasattr(date_value, "date"):
                session_date = date_value.date()
            else:
                session_date = pd.to_datetime(date_value).date()
            rows.append(
                BarRow(
                    session_date=session_date,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                )
            )
        return rows

    def _load_ohlcv_window(
        self,
        ticker: str,
        date: str,
        offset_n_days: Optional[int] = 85,
        actual_offset_n_days: Optional[int] = 50,
        utc_dates: bool = False,
    ) -> pd.DataFrame:
        offset_n_days = offset_n_days or 85
        actual_offset_n_days = actual_offset_n_days or 50
        end_date = pd.to_datetime(date)
        start_date = end_date - pd.Timedelta(days=offset_n_days)
        cache_ticker = self._normalize_cache_ticker(ticker)

        if not settings.OHLCV_CACHE_DISABLED:
            try:
                bars = fetch_bars(
                    self.market,
                    cache_ticker,
                    start_date.date(),
                    end_date.date(),
                )
                if len(bars) >= actual_offset_n_days:
                    max_session = max(bar.session_date for bar in bars)
                    if max_session >= end_date.date():
                        return self._bars_to_dataframe(bars, ticker, utc_dates)
            except Exception as exc:  # pylint: disable=broad-except
                print(f"providers/ohlcv_cache_mixin.py PG read failed: {exc}")

        df = self._fetch_ohlcv_from_api(
            ticker,
            date,
            offset_n_days,
            actual_offset_n_days,
            utc_dates,
        )
        if df.empty or settings.OHLCV_CACHE_DISABLED:
            return df

        try:
            upsert_bars(
                self.market,
                cache_ticker,
                self._dataframe_to_bar_rows(df),
            )
        except Exception as exc:  # pylint: disable=broad-except
            print(f"providers/ohlcv_cache_mixin.py PG write failed: {exc}")

        return df
