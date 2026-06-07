"""Close-price band definitions for Micro MarketEye screening."""

from typing import Optional, TypedDict


class PriceBandBounds(TypedDict):
    min: Optional[float]
    max: Optional[float]


PRICE_BANDS: dict[str, PriceBandBounds] = {
    "lte5": {"min": None, "max": 5.00},
    "5to10": {"min": 5.01, "max": 10.00},
    "10to20": {"min": 10.01, "max": 20.00},
    "20to50": {"min": 20.01, "max": 50.00},
}


def resolve_price_band(price_band: str) -> tuple[Optional[float], Optional[float]]:
    bounds = PRICE_BANDS[price_band]
    return bounds["min"], bounds["max"]
