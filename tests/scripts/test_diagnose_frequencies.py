"""Unit tests for diagnose_frequencies pure helpers."""

from scripts.diagnose_frequencies import (
    frequencies_from_membership,
    is_even_only,
    parse_t_ns,
)


def test_frequencies_from_membership_even_only():
    membership = [False, True, False, True, False]
    assert frequencies_from_membership(membership) == "T-2, T-4"


def test_frequencies_from_membership_empty():
    assert frequencies_from_membership([]) == ""
    assert frequencies_from_membership([False, False]) == ""


def test_is_even_only_detects_t2_t4():
    assert is_even_only("T-2, T-4") is True
    assert is_even_only("T-2, T-4, T-6") is True
    assert is_even_only("T-1, T-2, T-4") is False
    assert is_even_only("T-4") is False
    assert is_even_only("T-22") is False
    assert is_even_only("") is False


def test_parse_t_ns():
    assert parse_t_ns("T-2, T-4") == [2, 4]
