"""Parity: EODHD OCF → format_number_short matches Polygon-era golden strings."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from utils.handle_calculations import format_number_short
from utils.handle_external_apis import get_quarterly_free_cash_flow_eodhd

FIXTURES = (
    Path(__file__).resolve().parents[2] / "fixtures" / "fcf_parity.json"
)


def _load_parity():
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _load_parity()["cases"])
def test_polygon_era_ocf_format_golden(case):
    assert format_number_short(case["ocf"]) == case["formatted"]


@pytest.mark.parametrize("case", _load_parity()["cases"])
def test_eodhd_fcf_matches_polygon_era_formatted(case, monkeypatch):
    quarterly = {
        case["report_date"]: {
            "date": case["report_date"],
            "totalCashFromOperatingActivities": str(case["ocf"]),
        },
        "2099-01-01": {
            "date": "2099-01-01",
            "totalCashFromOperatingActivities": "1",
        },
    }
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json.return_value = quarterly

    monkeypatch.setattr(
        "utils.handle_external_apis.requests.get",
        lambda *a, **k: response,
    )

    assert (
        get_quarterly_free_cash_flow_eodhd(case["ticker"], case["date_quarter"])
        == case["formatted"]
    )
