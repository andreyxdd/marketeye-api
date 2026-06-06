"""US equities market data via Polygon.io."""

import threading
import time
from typing import Optional

import pandas as pd
import requests

from core.settings import POLYGON_API_KEY, PROBE_TICKER_US
from providers.analytics_mixin import (
    analytics_from_ohlcv,
    base_analytics_from_ohlcv_utc,
    extra_analytics_from_ohlcv,
)
from services.session_dates import session_dates_from_ohlcv

POLYGON_SYMBOL_ALIASES = {
    "GOOG": "GOOGL",
}

_thread_local = threading.local()


class PolygonUSProvider:
    market = "US"
    probe_ticker = PROBE_TICKER_US

    def _http_session(self) -> requests.Session:
        session = getattr(_thread_local, "polygon_session", None)
        if session is None:
            session = requests.Session()
            _thread_local.polygon_session = session
        return session

    def _http_get(self, url: str, **kwargs) -> requests.Response:
        return self._http_session().get(url, **kwargs)

    def _polygon_symbol(self, ticker: str) -> str:
        return POLYGON_SYMBOL_ALIASES.get(ticker.upper(), ticker.upper())

    def _polygon_aggs_url(
        self, ticker: str, start_date: pd.Timestamp, end_date: pd.Timestamp
    ) -> str:
        polygon_symbol = self._polygon_symbol(ticker)
        return (
            f"https://api.polygon.io/v2/aggs/ticker/{polygon_symbol}/range/1/day/"
            f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
            f"?adjusted=true&sort=desc&limit=50000&apiKey={POLYGON_API_KEY}"
        )

    def _request_json(self, url: str, max_attempts: int = 3) -> dict:
        backoff = 1
        last_error = None
        for attempt in range(max_attempts):
            try:
                response = self._http_get(url, timeout=60)
                if response.status_code == 429:
                    print(
                        f"providers/polygon_us.py: rate limit hit, sleeping {backoff}s"
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60)
                    continue
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt == max_attempts - 1:
                    break
                wait = min(backoff * (2**attempt), 30)
                print(
                    f"providers/polygon_us.py: request failed ({exc}), "
                    f"retry {attempt + 1}/{max_attempts - 1} in {wait}s"
                )
                time.sleep(wait)
        raise last_error

    def fetch_ohlcv(
        self,
        ticker: str,
        date: str,
        offset_n_days: Optional[int] = 85,
        actual_offset_n_days: Optional[int] = 50,
    ) -> pd.DataFrame:
        end_date = pd.to_datetime(date)
        start_date = end_date - pd.Timedelta(days=offset_n_days)
        url = self._polygon_aggs_url(ticker, start_date, end_date)

        data = self._request_json(url)

        results = data.get("results", [])
        if not results or len(results) < actual_offset_n_days:
            print(
                f"providers/polygon_us.py fetch_ohlcv: not enough EOD records "
                f"({len(results)}) for ticker {ticker}"
            )
            return pd.DataFrame()

        df = pd.DataFrame(results)
        df["date"] = pd.to_datetime(df["t"], unit="ms").dt.strftime("%Y-%m-%d")
        df = df.rename(
            columns={
                "o": "open",
                "h": "high",
                "l": "low",
                "c": "close",
                "v": "volume",
            }
        )
        df = df[["date", "open", "high", "low", "close", "volume"]]
        df["ticker"] = ticker.upper()
        return df

    def fetch_ohlcv_utc(
        self,
        ticker: str,
        date: str,
        offset_n_days: Optional[int] = 85,
        actual_offset_n_days: Optional[int] = 50,
    ) -> pd.DataFrame:
        """OHLCV with UTC-aware timestamps (pipeline insert path)."""
        end_date = pd.to_datetime(date)
        start_date = end_date - pd.Timedelta(days=offset_n_days)
        url = self._polygon_aggs_url(ticker, start_date, end_date)

        data = self._request_json(url)

        results = data.get("results", [])
        if not results or len(results) < actual_offset_n_days:
            print(
                f"providers/polygon_us.py fetch_ohlcv_utc: not enough EOD records "
                f"({len(results)}) for ticker {ticker}"
            )
            return pd.DataFrame()

        df = pd.DataFrame(results)
        df["t"] = pd.to_datetime(df["t"], unit="ms", utc=True)
        df = df.rename(
            columns={
                "t": "date",
                "o": "open",
                "h": "high",
                "l": "low",
                "c": "close",
                "v": "volume",
            }
        )
        df = df[["date", "open", "high", "low", "close", "volume"]]
        df["ticker"] = ticker.upper()
        return df

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
        url = (
            f"https://api.polygon.io/v3/reference/tickers?market=stocks&active=true"
            f"&apiKey={POLYGON_API_KEY}&limit=1000&date={date}"
        )
        tickers = []
        backoff = 1

        while url:
            response = self._http_get(url)
            if response.status_code == 429:
                print(
                    f"providers/polygon_us.py fetch_ticker_universe: "
                    f"rate limit hit, sleeping {backoff}s"
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            response.raise_for_status()

            data = response.json()
            tickers.extend(item["ticker"] for item in data.get("results", []))

            url = data.get("next_url")
            if url:
                url += f"&apiKey={POLYGON_API_KEY}"
            backoff = 1

        return tickers
