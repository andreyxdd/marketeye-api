"""Market data provider registry."""

from providers.base import MarketDataProvider
from providers.eodhd_to import EodhdTOProvider
from providers.polygon_us import PolygonUSProvider

_DEFAULT_US_PROVIDER = PolygonUSProvider()
_DEFAULT_TO_PROVIDER = EodhdTOProvider()

_PROVIDERS: dict[str, MarketDataProvider] = {
    "US": _DEFAULT_US_PROVIDER,
    "TO": _DEFAULT_TO_PROVIDER,
}


def get_market_data_provider(market: str = "US") -> MarketDataProvider:
    code = market.upper()
    provider = _PROVIDERS.get(code)
    if provider is None:
        raise ValueError(f"unsupported market: {market}")
    return provider


def list_market_providers() -> list[str]:
    return list(_PROVIDERS.keys())
