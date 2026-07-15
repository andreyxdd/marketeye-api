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

MARKETS = ("US", "TO")


def _dates_response(date_string: str) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = [{"date_string": date_string}]
    response.raise_for_status.return_value = None
    return response


def _mock_provider(last_session: str, prior_session: str = "2024-06-02") -> MagicMock:
    provider = MagicMock()
    provider.resolve_session_dates.return_value = (last_session, prior_session)
    return provider


def test_run_test_api_success_when_both_markets_match_last_session(monkeypatch):
    """API latest date equals LastCompletedSession for US and TO."""
    calls = []

    def fake_get(url, timeout=30):
        calls.append(url)
        if "market=US" in url:
            return _dates_response("2024-06-03")
        if "market=TO" in url:
            return _dates_response("2024-06-03")
        raise AssertionError(f"unexpected url: {url}")

    providers = {"US": _mock_provider("2024-06-03"), "TO": _mock_provider("2024-06-03")}

    monkeypatch.setenv("PING_URL", "https://api.example.com")
    monkeypatch.setenv("API_KEY", "secret")
    monkeypatch.setattr(test_api.requests, "get", fake_get)
    monkeypatch.setattr(
        test_api,
        "get_market_data_provider",
        lambda market: providers[market],
    )
    monkeypatch.setattr(test_api, "_calendar_end_for_market", lambda market: "2024-06-04")

    test_api.run_test_api()

    assert any("market=US" in u for u in calls)
    assert any("market=TO" in u for u in calls)
    for market in MARKETS:
        providers[market].resolve_session_dates.assert_called_once_with("2024-06-04")


def test_run_test_api_raises_when_stale_vs_last_session(monkeypatch):
    """Fail when API date lags LastCompletedSession."""

    def fake_get(url, timeout=30):
        if "market=US" in url:
            return _dates_response("2024-06-01")
        if "market=TO" in url:
            return _dates_response("2024-06-03")
        raise AssertionError(f"unexpected url: {url}")

    providers = {"US": _mock_provider("2024-06-03"), "TO": _mock_provider("2024-06-03")}

    monkeypatch.setenv("PING_URL", "https://api.example.com")
    monkeypatch.setenv("API_KEY", "secret")
    monkeypatch.setattr(test_api.requests, "get", fake_get)
    monkeypatch.setattr(
        test_api,
        "get_market_data_provider",
        lambda market: providers[market],
    )
    monkeypatch.setattr(test_api, "_calendar_end_for_market", lambda market: "2024-06-03")

    with pytest.raises(RuntimeError, match=r"US.*2024-06-01.*2024-06-03"):
        test_api.run_test_api()


def test_run_test_api_ok_when_calendar_ahead_of_session(monkeypatch):
    """Calendar day ahead of LastCompletedSession is not treated as expected date."""

    def fake_get(url, timeout=30):
        return _dates_response("2024-06-03")

    providers = {"US": _mock_provider("2024-06-03"), "TO": _mock_provider("2024-06-03")}

    monkeypatch.setenv("PING_URL", "https://api.example.com")
    monkeypatch.setenv("API_KEY", "secret")
    monkeypatch.setattr(test_api.requests, "get", fake_get)
    monkeypatch.setattr(
        test_api,
        "get_market_data_provider",
        lambda market: providers[market],
    )
    # Local calendar is 2024-06-04; session is still 2024-06-03 — must pass.
    monkeypatch.setattr(test_api, "_calendar_end_for_market", lambda market: "2024-06-04")

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
