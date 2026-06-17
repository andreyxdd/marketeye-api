"""Unit tests for infra healthcheck monitor."""

from unittest.mock import MagicMock

import pytest

import scripts.healthcheck_monitor as healthcheck_monitor


def test_run_healthcheck_success(monkeypatch):
    responses = {
        "/healthz": (200, '{"status":"ok"}'),
        "/readyz": (200, '{"status":"ok","mongo":"ok"}'),
    }

    def fake_probe(path, ping_url=None):
        del ping_url
        return responses[path]

    monkeypatch.setattr(healthcheck_monitor, "_probe", fake_probe)
    monkeypatch.setenv("PING_URL", "https://api.example.com")

    result = healthcheck_monitor.run_healthcheck()

    assert result["/healthz"]["status_code"] == 200
    assert result["/readyz"]["status_code"] == 200


def test_run_healthcheck_fails_on_non_200(monkeypatch):
    def fake_probe(path, ping_url=None):
        del ping_url
        if path == "/readyz":
            return 503, '{"status":"unavailable","mongo":"down"}'
        return 200, '{"status":"ok"}'

    monkeypatch.setattr(healthcheck_monitor, "_probe", fake_probe)
    monkeypatch.setenv("PING_URL", "https://api.example.com")

    with pytest.raises(RuntimeError, match="/readyz returned HTTP 503"):
        healthcheck_monitor.run_healthcheck()


def test_main_notifies_and_exits_nonzero_on_failure(monkeypatch):
    calls = []

    def fail_healthcheck(ping_url=None):
        del ping_url
        raise RuntimeError("/readyz returned HTTP 503")

    monkeypatch.setattr(healthcheck_monitor, "run_healthcheck", fail_healthcheck)
    monkeypatch.setattr(
        healthcheck_monitor,
        "notify_developer",
        lambda **kwargs: calls.append(kwargs),
    )

    assert healthcheck_monitor.main() == 1
    assert calls == [
        {
            "subject": "Infra health check failed",
            "body": "/readyz returned HTTP 503",
        }
    ]


def test_main_returns_zero_on_success(monkeypatch):
    monkeypatch.setattr(
        healthcheck_monitor,
        "run_healthcheck",
        lambda ping_url=None: {"/healthz": {"status_code": 200}, "/readyz": {"status_code": 200}},
    )

    assert healthcheck_monitor.main() == 0
