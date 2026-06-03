"""Market data provider registry."""

from providers.base import MarketDataProvider
from providers.polygon_us import PolygonUSProvider

_DEFAULT_US_PROVIDER = PolygonUSProvider()


def get_market_data_provider(market: str = "US") -> MarketDataProvider:
    if market.upper() == "US":
        return _DEFAULT_US_PROVIDER
    raise ValueError(f"unsupported market: {market}")
