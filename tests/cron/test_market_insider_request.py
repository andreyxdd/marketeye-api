"""Market Insider request resilience."""

from unittest.mock import MagicMock

import pytest
from requests.exceptions import Timeout

from utils import handle_external_apis as external


def test_market_insider_request_retries_on_500(monkeypatch):
    responses = [
        MagicMock(status_code=500, text="error"),
        MagicMock(status_code=500, text="error"),
        MagicMock(status_code=200, text='[{"Close": 1}]'),
    ]

    def fake_get(url, headers=None, timeout=None):
        return responses.pop(0)

    monkeypatch.setattr(external, "get", fake_get)
    monkeypatch.setattr(external, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        external,
        "DEFAULT_HEADERS",
        {"user-agent": "test-agent"},
    )

    response = external._market_insider_request("https://example.test/sp500", "S&P")
    assert response.status_code == 200


def test_market_insider_request_raises_after_exhausted_retries(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return MagicMock(status_code=503, text="unavailable")

    monkeypatch.setattr(external, "get", fake_get)
    monkeypatch.setattr(external, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        external,
        "DEFAULT_HEADERS",
        {"user-agent": "test-agent"},
    )

    with pytest.raises(Exception, match="503"):
        external._market_insider_request("https://example.test/sp500", "S&P")


def test_market_insider_request_retries_on_timeout(monkeypatch):
    calls = {"count": 0}

    def fake_get(url, headers=None, timeout=None):
        calls["count"] += 1
        if calls["count"] < 2:
            raise Timeout("timed out")
        return MagicMock(status_code=200, text="[]")

    monkeypatch.setattr(external, "get", fake_get)
    monkeypatch.setattr(external, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        external,
        "DEFAULT_HEADERS",
        {"user-agent": "test-agent"},
    )

    response = external._market_insider_request("https://example.test/vix", "VIX")
    assert response.status_code == 200
    assert calls["count"] == 2
