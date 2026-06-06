"""Market data provider protocol (Phase 2 extension point)."""

from typing import Optional, Protocol

import pandas as pd


class MarketDataProvider(Protocol):
    market: str

    def fetch_ohlcv(
        self,
        ticker: str,
        date: str,
        offset_n_days: Optional[int] = 85,
        actual_offset_n_days: Optional[int] = 50,
    ) -> pd.DataFrame:
        """Return normalized OHLCV rows: date, open, high, low, close, volume, ticker."""

    def fetch_ticker_analytics(
        self,
        ticker: str,
        date: str,
        offset_n_days: Optional[int] = 85,
        actual_offset_n_days: Optional[int] = 50,
        test_offset: Optional[bool] = False,
    ) -> dict:
        """Base + extra analytics for one ticker."""

    def fetch_ticker_base_analytics(
        self,
        ticker: str,
        date: str,
        offset_n_days: Optional[int] = 85,
        actual_offset_n_days: Optional[int] = 50,
    ) -> dict:
        """Base analytics only (pipeline insert path)."""

    def fetch_ticker_universe(self, date: str) -> list[str]:
        """All tickers available for the market on the given date."""

    def fetch_ticker_extra_analytics(
        self,
        ticker: str,
        date: str,
        offset_n_days: Optional[int] = 85,
        actual_offset_n_days: Optional[int] = 50,
    ) -> dict:
        """Extra analytics (e.g. mfi) derived from OHLCV."""

    @property
    def probe_ticker(self) -> str:
        """Liquid benchmark ticker for session-date probing."""

    def resolve_session_dates(
        self, date: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Return (LastCompletedSession, PriorCompletedSession) for the market."""
