"""Tests for the clock dyno's pure slot helpers."""

from datetime import datetime, timezone

import pytest

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
