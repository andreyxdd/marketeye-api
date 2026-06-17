"""Unit tests for API freshness monitor script."""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("test_api", ROOT / "test-api.py")
test_api = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(test_api)


def test_run_test_api_success(monkeypatch):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = [{"date_string": "2024-06-03"}]
    response.raise_for_status.return_value = None

    monkeypatch.setenv("PING_URL", "https://api.example.com")
    monkeypatch.setenv("API_KEY", "secret")
    monkeypatch.setattr(
        test_api,
        "get_today_utc_date_in_timezone",
        lambda tz: "2024-06-03",
    )
    monkeypatch.setattr(test_api.requests, "get", lambda *args, **kwargs: response)

    test_api.run_test_api()


def test_run_test_api_raises_on_stale_date(monkeypatch):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = [{"date_string": "2024-06-01"}]
    response.raise_for_status.return_value = None

    monkeypatch.setenv("PING_URL", "https://api.example.com")
    monkeypatch.setenv("API_KEY", "secret")
    monkeypatch.setattr(
        test_api,
        "get_today_utc_date_in_timezone",
        lambda tz: "2024-06-03",
    )
    monkeypatch.setattr(test_api.requests, "get", lambda *args, **kwargs: response)

    with pytest.raises(RuntimeError, match="latest date 2024-06-01"):
        test_api.run_test_api()


def test_main_notifies_and_exits_nonzero_on_failure(monkeypatch):
    calls = []

    def fail_run():
        raise RuntimeError("stale date")

    monkeypatch.setattr(test_api, "run_test_api", fail_run)
    monkeypatch.setattr(
        test_api,
        "notify_developer",
        lambda **kwargs: calls.append(kwargs),
    )

    assert test_api.main() == 1
    assert calls[0]["subject"] == "API freshness check failed"
    assert "stale date" in calls[0]["body"]


def test_main_returns_zero_on_success(monkeypatch):
    monkeypatch.setattr(test_api, "run_test_api", lambda: None)
    assert test_api.main() == 0
