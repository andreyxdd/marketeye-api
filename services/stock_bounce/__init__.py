"""Canonical StockBounce snapshots and legacy-compatible pure semantics."""

from .semantics import (
    PRICE_RANGES,
    build_snapshot,
    build_stock_bounce_analytics,
    evaluate,
)

__all__ = [
    "PRICE_RANGES",
    "build_snapshot",
    "build_stock_bounce_analytics",
    "evaluate",
]
