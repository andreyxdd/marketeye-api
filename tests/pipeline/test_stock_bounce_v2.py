"""Independent contract fixtures for StockBounce v2 screening semantics."""

import pytest

from services.stock_bounce.semantics_v2 import evaluate_v2


def _row(ticker, *, universes, high=111.0, previous_high=110.0, close=105.0):
    return {
        "ticker": ticker,
        "open": 100.0,
        "high": high,
        "close": close,
        "volume": 1234,
        "previous_all_time_high": previous_high,
        "universes": list(universes),
    }


def _snapshot(rows):
    return {
        "schema_version": 2,
        "market": "US",
        "date": "2024-03-05",
        "max_lookback": 20,
        "rows": rows,
        "coverage": {
            universe: {
                "status": "exact",
                "universe_provenance": "fixture_universe",
                "exclusions_count": 0,
            }
            for universe in ("whole_market", "macd_history")
        },
    }


def _bar(ticker, day, open_price, close_price):
    return {
        "ticker": ticker,
        "date": day,
        "open": open_price,
        "close": close_price,
    }


def test_evaluate_v2_uses_signed_t_minus_one_window_and_independent_top_lists():
    snapshot = _snapshot(
        [
            _row("BOTH", universes=("whole_market", "macd_history")),
            _row("MARKET", universes=("whole_market",), close=104.0),
            _row("MACD", universes=("macd_history",), close=103.0),
            _row("TIE", universes=("whole_market", "macd_history"), high=110.0),
            _row("FLAT", universes=("whole_market",), close=100.0),
        ]
    )
    bars = []
    for ticker in ("BOTH", "MARKET", "MACD", "TIE", "FLAT"):
        bars.extend(
            [
                _bar(ticker, "2024-03-01", 100.0, 99.0),
                _bar(ticker, "2024-03-04", 98.0, 90.0),
            ]
        )

    result = evaluate_v2(snapshot, bars, lookback=2)

    assert result["schema_version"] == 2
    assert result["lookback"] == 2
    assert [row["ticker"] for row in result["whole_market"]["rows"]] == [
        "BOTH",
        "MARKET",
    ]
    assert [row["ticker"] for row in result["macd_history"]["rows"]] == [
        "BOTH",
        "MACD",
    ]
    row = result["whole_market"]["rows"][0]
    assert row["lookback_change_pct"] == pytest.approx(-10.0)
    assert row["open_close_change_pct"] == pytest.approx(5.0)
    assert row["high"] == 111.0
    assert row["previous_all_time_high"] == 110.0


def test_lookback_one_is_previous_session_open_to_close_not_cumulative_change():
    snapshot = _snapshot([_row("ABC", universes=("whole_market",))])
    bars = [
        _bar("ABC", "2024-03-01", 500.0, 400.0),
        _bar("ABC", "2024-03-04", 100.0, 95.0),
    ]

    result = evaluate_v2(snapshot, bars, lookback=1)

    assert result["whole_market"]["rows"][0]["lookback_change_pct"] == -5.0


def test_decline_positive_day_and_strict_new_high_filters_precede_ranking():
    rows = [
        _row("SLOW", universes=("whole_market",), close=101.0),
        _row("FAST", universes=("whole_market",), close=110.0),
        _row("TIEDHIGH", universes=("whole_market",), high=110.0, close=120.0),
        _row("NOTNEW", universes=("whole_market",), high=109.0, close=130.0),
    ]
    bars = []
    for ticker in ("SLOW", "FAST", "TIEDHIGH", "NOTNEW"):
        bars.extend(
            [
                _bar(ticker, "2024-03-04", 100.0, 95.0),
            ]
        )
    bars.append(_bar("NOTNEW", "2024-03-04", 100.0, 95.0))

    result = evaluate_v2(_snapshot(rows), bars, lookback=1)

    assert [row["ticker"] for row in result["whole_market"]["rows"]] == [
        "FAST",
        "SLOW",
    ]


def test_nonnegative_lookback_and_missing_bars_are_excluded_without_partial_periods():
    rows = [
        _row("NOBARS", universes=("whole_market",)),
        _row("RISE", universes=("whole_market",)),
        _row("GOOD", universes=("whole_market",)),
    ]
    bars = [
        _bar("RISE", "2024-03-04", 100.0, 100.0),
        _bar("GOOD", "2024-03-04", 100.0, 99.0),
    ]

    result = evaluate_v2(_snapshot(rows), bars, lookback=1)

    assert [row["ticker"] for row in result["whole_market"]["rows"]] == ["GOOD"]
    assert result["whole_market"]["coverage"]["exclusions_count"] == 1
    assert result["macd_history"]["coverage"]["exclusions_count"] == 0


def test_legacy_snapshot_without_unseeded_count_preserves_unknown_coverage():
    result = evaluate_v2(_snapshot([]), [], lookback=1)

    assert result["whole_market"]["coverage"]["unseeded_count"] is None
    assert result["macd_history"]["coverage"]["unseeded_count"] is None
