"""Bounce HTTP API is intentionally unmounted (legacy bounce app)."""

from api import router
from main import tags_metadata


def test_bounce_router_not_mounted():
    paths = [getattr(route, "path", "") or "" for route in router.routes]
    assert not any(path.startswith("/bounce") for path in paths)


def test_openapi_tags_omit_bounce():
    names = {tag.get("name") for tag in tags_metadata}
    assert "Bounce" not in names
