"""Market registry — venue codes, timezones, provider bindings."""

from typing import Optional, TypedDict


class MarketConfig(TypedDict):
    provider: str
    timezone: str
    eodhd_exchange: Optional[str]


MARKETS: dict[str, MarketConfig] = {
    "US": {
        "provider": "polygon",
        "timezone": "America/New_York",
        "eodhd_exchange": None,
    },
    "TO": {
        "provider": "eodhd",
        "timezone": "America/Toronto",
        "eodhd_exchange": "TO",
    },
}

DEFAULT_MARKET = "US"


def normalize_market(market: str) -> str:
    code = market.upper()
    if code not in MARKETS:
        raise ValueError(f"unsupported market: {market}")
    return code


def list_markets() -> list[str]:
    return list(MARKETS.keys())


def market_mongo_filter(market: str) -> dict:
    """Match docs for a venue; US includes legacy rows without market field."""
    code = normalize_market(market)
    if code == "US":
        return {"$or": [{"market": "US"}, {"market": {"$exists": False}}]}
    return {"market": code}
