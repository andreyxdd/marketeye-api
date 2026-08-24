"""Unit tests for CVI slope normalization edge cases."""

import json
import math

from db.crud.published_archive import _dumps_payload
from utils.handle_calculations import get_slope_normalized


def test_get_slope_normalized_flat_series_returns_neutral():
    slope = get_slope_normalized([1, 2, 3, 4, 5], [10, 10, 10, 10, 10])
    assert slope == 0.5
    assert math.isfinite(slope)


def test_dumps_payload_strips_non_finite_floats():
    payload = {"slope": float("inf"), "nested": [{"value": float("nan")}]}
    decoded = json.loads(_dumps_payload(payload))
    assert decoded == {"slope": None, "nested": [{"value": None}]}
