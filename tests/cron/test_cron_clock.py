"""Tests for the clock dyno's pure slot helpers."""

from datetime import datetime, timezone

import subprocess

import pytest

import scripts.cron_clock as cron_clock
from scripts.cron_clock import DEFAULT_SLOTS, next_slot, parse_slots


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_parse_slots_reads_hh_mm_list():
    assert parse_slots("20:07, 00:37,3:07") == [(20, 7), (0, 37), (3, 7)]


@pytest.mark.parametrize("raw", ["", "20:07,", "2007", "24:00", "12:60", "ab:cd", "-1:05"])
def test_parse_slots_rejects_malformed(raw):
    with pytest.raises(ValueError):
        parse_slots(raw)


def test_default_slots_match_github_schedule():
    assert parse_slots(DEFAULT_SLOTS) == [
        (20, 7), (20, 37), (21, 7), (21, 37), (22, 7), (22, 37), (23, 7), (23, 37),
        (0, 7), (0, 37), (1, 7), (1, 37), (2, 7), (2, 37), (3, 7),
    ]


SLOTS = [(20, 7), (23, 37), (0, 7), (3, 7)]


@pytest.mark.parametrize(
    "now, expected",
    [
        (_utc(2026, 11, 25, 12, 0), _utc(2026, 11, 25, 20, 7)),
        # exactly on a slot -> strictly after
        (_utc(2026, 11, 25, 20, 7), _utc(2026, 11, 25, 23, 37)),
        # across midnight
        (_utc(2026, 11, 25, 23, 50), _utc(2026, 11, 26, 0, 7)),
        (_utc(2026, 11, 26, 0, 8), _utc(2026, 11, 26, 3, 7)),
        # after the last slot of the night, wraps to the next evening
        (_utc(2026, 11, 26, 3, 7, 1), _utc(2026, 11, 26, 20, 7)),
        # month/year rollover
        (_utc(2026, 12, 31, 23, 40), _utc(2027, 1, 1, 0, 7)),
    ],
)
def test_next_slot(now, expected):
    assert next_slot(now, SLOTS) == expected


def test_run_slot_probe_timeout_skips_cronjob(monkeypatch, capsys):
    calls = []

    def run_stub(cmd, **kwargs):
        calls.append(cmd)
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr(cron_clock.subprocess, "run", run_stub)
    monkeypatch.setattr(cron_clock, "alert_timeout", lambda *a: None)

    cron_clock.run_slot("20:07")

    assert len(calls) == 1 and calls[0][-1] == "scripts/cron_probe.py"
    out = capsys.readouterr().out
    assert "timeout: scripts/cron_probe.py" in out
    assert "cron_clock slot=20:07 needs_work=false exit=timeout" in out


def test_run_slot_cronjob_timeout_alerts_and_continues(monkeypatch, capsys):
    alerts = []

    def run_stub(cmd, **kwargs):
        if cmd[-1] == "scripts/cron_probe.py":
            return subprocess.CompletedProcess(cmd, 0, stdout="needs_work=true\n", stderr="")
        assert kwargs["timeout"] == cron_clock.CRONJOB_TIMEOUT_S
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(cron_clock.subprocess, "run", run_stub)
    monkeypatch.setattr(cron_clock, "alert_timeout", lambda label, err: alerts.append(label))

    cron_clock.run_slot("21:37")

    out = capsys.readouterr().out
    assert alerts == ["21:37"]
    assert "cron_clock slot=21:37 timeout: cronjob.py" in out
    assert "cron_clock slot=21:37 needs_work=true exit=timeout" in out
