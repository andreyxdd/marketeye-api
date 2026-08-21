"""US equities market data via EODHD (.US)."""

import time

from core.settings import EODHD_API_KEY, PROBE_TICKER_US
from providers.eodhd_to import EODHD_BASE_URL, EodhdTOProvider


class EodhdUSProvider(EodhdTOProvider):
    market = "US"
    probe_ticker = PROBE_TICKER_US

    def _eod_symbol(self, ticker: str) -> str:
        return f"{ticker.upper()}.US"

    def fetch_ticker_universe(self, date: str) -> list[str]:
        del date
        tickers: list[str] = []
        seen: set[str] = set()
        for exchange in ("NYSE", "NASDAQ"):
            url = (
                f"{EODHD_BASE_URL}/exchange-symbol-list/{exchange}"
                f"?api_token={EODHD_API_KEY}&fmt=json"
            )
            backoff = 1
            while True:
                response = self._http_get(url)
                if response.status_code == 429:
                    print(
                        f"providers/eodhd_us.py fetch_ticker_universe: "
                        f"rate limit hit on {exchange}, sleeping {backoff}s"
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60)
                    continue
                response.raise_for_status()
                break

            data = response.json()
            if not isinstance(data, list):
                raise ValueError(
                    f"providers/eodhd_us.py fetch_ticker_universe: "
                    f"expected list from {exchange}, got {type(data).__name__}: {data!r}"
                )
            for item in data:
                if not isinstance(item, dict):
                    continue
                code = item.get("Code") or item.get("code")
                asset_type = (item.get("Type") or item.get("type") or "").lower()
                if not code:
                    continue
                if asset_type and asset_type not in ("common stock", "stock"):
                    continue
                upper = code.upper()
                if upper in seen:
                    continue
                seen.add(upper)
                tickers.append(upper)
        return tickers
