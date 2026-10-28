"""Only the versioned StockBounce API is mounted; legacy get_* routes stay disabled."""

from api import router


def test_legacy_bounce_router_not_mounted():
    paths = [getattr(route, "path", "") or "" for route in router.routes]
    assert not any(path.startswith("/bounce") for path in paths)
    assert not any("get_bounce_stocks" in path for path in paths)


def test_stock_bounce_v1_router_is_mounted():
    paths = [getattr(route, "path", "") or "" for route in router.routes]
    assert "/stock-bounce/v1/sessions" in paths
    assert "/stock-bounce/v1/results" in paths
