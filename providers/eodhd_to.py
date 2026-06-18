"""Toronto Stock Exchange (TO) market data via EODHD."""

import threading
import time
from typing import Optional

import pandas as pd
import requests

from core.settings import EODHD_API_KEY, PROBE_TICKER_TO
from providers.analytics_mixin import (
    analytics_from_ohlcv,
    base_analytics_from_ohlcv_utc,
    extra_analytics_from_ohlcv,
)
from providers.ohlcv_cache_mixin import OhlcvCacheMixin
from services.session_dates import session_dates_from_ohlcv

EODHD_BASE_URL = "https://eodhd.com/api"

_thread_local = threading.local()


class EodhdTOProvider(OhlcvCacheMixin):
    market = "TO"
    probe_ticker = PROBE_TICKER_TO

    def _http_session(self) -> requests.Session:
        session = getattr(_thread_local, "eodhd_session", None)
        if session is None:
            session = requests.Session()
            _thread_local.eodhd_session = session
        return session

    def _http_get(self, url: str, **kwargs) -> requests.Response:
        return self._http_session().get(url, **kwargs)

    def _eod_symbol(self, ticker: str) -> str:
        return f"{ticker.upper()}.TO"

    def _eod_url(self, ticker: str, start_date: pd.Timestamp, end_date: pd.Timestamp) -> str:
        symbol = self._eod_symbol(ticker)
        return (
            f"{EODHD_BASE_URL}/eod/{symbol}"
            f"?from={start_date.strftime('%Y-%m-%d')}"
            f"&to={end_date.strftime('%Y-%m-%d')}"
            f"&period=d&fmt=json&api_token={EODHD_API_KEY}"
        )

    def _fetch_ohlcv_from_api(
        self,
        ticker: str,
        date: str,
        offset_n_days: int,
        actual_offset_n_days: int,
        utc_dates: bool,
    ) -> pd.DataFrame:
        end_date = pd.to_datetime(date)
        start_date = end_date - pd.Timedelta(days=offset_n_days)
        url = self._eod_url(ticker, start_date, end_date)

        backoff = 1
        while True:
            response = self._http_get(url)
            if response.status_code == 429:
                print(
                    f"providers/eodhd_to.py: rate limit hit for {ticker}, "
                    f"sleeping {backoff}s"
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            response.raise_for_status()
            break

        results = response.json()
        if not isinstance(results, list):
            results = []

        if not results or len(results) < actual_offset_n_days:
            print(
                f"providers/eodhd_to.py: not enough EOD records "
                f"({len(results)}) for ticker {ticker}"
            )
            return pd.DataFrame()

        df = pd.DataFrame(results)
        if utc_dates:
            df["date"] = pd.to_datetime(df["date"], utc=True)
        else:
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

        df = df.rename(
            columns={
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            }
        )
        df = df[["date", "open", "high", "low", "close", "volume"]]
        df["ticker"] = ticker.upper()
        return df

    def _fetch_eod_dataframe(
        self,
        ticker: str,
        date: str,
        offset_n_days: int,
        actual_offset_n_days: int,
        utc_dates: bool,
    ) -> pd.DataFrame:
        return self._load_ohlcv_window(
            ticker,
            date,
            offset_n_days,
            actual_offset_n_days,
            utc_dates=utc_dates,
        )

    def fetch_ohlcv(
        self,
        ticker: str,
        date: str,
        offset_n_days: Optional[int] = 85,
        actual_offset_n_days: Optional[int] = 50,
    ) -> pd.DataFrame:
        return self._fetch_eod_dataframe(
            ticker, date, offset_n_days, actual_offset_n_days, utc_dates=False
        )

    def fetch_ohlcv_utc(
        self,
        ticker: str,
        date: str,
        offset_n_days: Optional[int] = 85,
        actual_offset_n_days: Optional[int] = 50,
    ) -> pd.DataFrame:
        return self._fetch_eod_dataframe(
            ticker, date, offset_n_days, actual_offset_n_days, utc_dates=True
        )

    def fetch_ticker_extra_analytics(
        self,
        ticker: str,
        date: str,
        offset_n_days: Optional[int] = 85,
        actual_offset_n_days: Optional[int] = 50,
    ) -> dict:
        df = self.fetch_ohlcv(ticker, date, offset_n_days, actual_offset_n_days)
        return extra_analytics_from_ohlcv(df)

    def fetch_ticker_analytics(
        self,
        ticker: str,
        date: str,
        offset_n_days: Optional[int] = 85,
        actual_offset_n_days: Optional[int] = 50,
        test_offset: Optional[bool] = False,
    ) -> dict:
        del test_offset
        df = self.fetch_ohlcv(ticker, date, offset_n_days, actual_offset_n_days)
        return analytics_from_ohlcv(df)

    def fetch_ticker_base_analytics(
        self,
        ticker: str,
        date: str,
        offset_n_days: Optional[int] = 85,
        actual_offset_n_days: Optional[int] = 50,
    ) -> dict:
        df = self.fetch_ohlcv_utc(ticker, date, offset_n_days, actual_offset_n_days)
        return base_analytics_from_ohlcv_utc(df)

    def resolve_session_dates(
        self, date: str
    ) -> tuple[Optional[str], Optional[str]]:
        df = self.fetch_ohlcv(
            self.probe_ticker, date, offset_n_days=10, actual_offset_n_days=2
        )
        return session_dates_from_ohlcv(df)

    def fetch_ticker_universe(self, date: str) -> list[str]:
        del date
        url = (
            f"{EODHD_BASE_URL}/exchange-symbol-list/TO"
            f"?api_token={EODHD_API_KEY}&fmt=json"
        )
        backoff = 1
        while True:
            response = self._http_get(url)
            if response.status_code == 429:
                print(
                    f"providers/eodhd_to.py fetch_ticker_universe: "
                    f"rate limit hit, sleeping {backoff}s"
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            response.raise_for_status()
            break

        data = response.json()
        tickers = []
        for item in data:
            code = item.get("Code") or item.get("code")
            asset_type = (item.get("Type") or item.get("type") or "").lower()
            if not code:
                continue
            if asset_type and asset_type not in ("common stock", "stock"):
                continue
            tickers.append(code.upper())
        return tickers
