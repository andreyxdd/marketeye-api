"""Representative deterministic in-process v2 evaluation performance gate."""

from statistics import quantiles
from time import perf_counter

from services.stock_bounce.semantics_v2 import evaluate_v2


def test_six_thousand_ticker_five_year_evaluation_p95_below_two_seconds():
    rows = [
        {
            "ticker": f"T{index:05d}",
            "open": 100.0,
            "high": 111.0,
            "close": 101.0 + (index % 20) / 10,
            "volume": 1000 + index,
            "previous_all_time_high": 110.0,
            "universes": ["whole_market", "macd_history"],
        }
        for index in range(6000)
    ]
    snapshot = {
        "schema_version": 2,
        "market": "US",
        "date": "2024-12-31",
        "max_lookback": 1260,
        "rows": rows,
        "coverage": {
            universe: {
                "status": "exact",
                "universe_provenance": "performance_fixture",
                "exclusions_count": 0,
            }
            for universe in ("whole_market", "macd_history")
        },
    }
    bars = [
        {
            "ticker": row["ticker"],
            "date": day,
            "open": 100.0,
            "close": close,
        }
        for row in rows
        for day, close in (("2019-12-31", 100.0), ("2024-12-30", 90.0))
    ]

    durations = []
    for _ in range(9):
        started = perf_counter()
        result = evaluate_v2(snapshot, bars, lookback=1260)
        durations.append(perf_counter() - started)

    assert len(result["whole_market"]["rows"]) == 20
    assert len(result["macd_history"]["rows"]) == 20
    p95 = quantiles(durations, n=20, method="inclusive")[-1]
    assert p95 < 2.0, f"v2 evaluation p95={p95:.3f}s"
