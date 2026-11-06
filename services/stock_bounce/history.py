"""Split-only comparisons and incremental all-time-high watermark state."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Iterable, Optional


def _date_value(value) -> str:
    if isinstance(value, str):
        return value[:10]
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    raise ValueError("invalid history date")


def split_ratio(split: dict) -> float:
    """Return new shares per old share for an explicit provider split event."""
    value = split.get("ratio", split.get("split"))
    if value is not None:
        if isinstance(value, str) and (":" in value or "/" in value):
            separator = ":" if ":" in value else "/"
            numerator, denominator = value.split(separator, 1)
            ratio = float(numerator) / float(denominator)
        else:
            ratio = float(value)
    else:
        ratio = float(split["numerator"]) / float(split["denominator"])
    if not math.isfinite(ratio) or ratio <= 0:
        raise ValueError("split ratio must be positive and finite")
    return ratio


def split_adjustment_factor(
    splits: Iterable[dict], from_date: str, through_date: str
) -> float:
    start = _date_value(from_date)
    end = _date_value(through_date)
    factor = 1.0
    for split in splits:
        split_date = _date_value(split.get("date", split.get("split_date")))
        if start < split_date <= end:
            factor *= split_ratio(split)
    return factor


def adjust_high(
    high: float, bar_date: str, through_date: str, splits: Iterable[dict]
) -> float:
    return float(high) / split_adjustment_factor(splits, bar_date, through_date)


def previous_all_time_high(
    bars: Iterable[dict], target_date: str, splits: Iterable[dict]
) -> Optional[float]:
    """Compute the strict pre-T high on T's split-adjusted basis."""
    target = _date_value(target_date)
    split_list = list(splits)
    highs = [
        adjust_high(bar["high"], _date_value(bar["date"]), target, split_list)
        for bar in bars
        if _date_value(bar["date"]) < target
    ]
    return max(highs) if highs else None


def advance_high_watermark(
    watermark: Optional[dict], target_bar: dict, splits: Iterable[dict]
) -> tuple[Optional[float], dict]:
    """Rescale stored history and advance it with exactly one new target bar."""
    target_date = _date_value(target_bar["date"])
    target_high = float(target_bar["high"])
    if not math.isfinite(target_high):
        raise ValueError("target high must be finite")
    if watermark is None:
        return None, {"date": target_date, "high": target_high}
    previous = adjust_high(
        watermark["high"], _date_value(watermark["date"]), target_date, splits
    )
    return previous, {
        "date": target_date,
        "high": max(previous, target_high),
    }


def bounded_bars(
    bars: Iterable[dict],
    first_target: str,
    last_target: str,
    max_prior_bars: int = 1260,
) -> list[dict]:
    """Retain only the supported lookback window and requested result sessions."""
    ordered = sorted(bars, key=lambda bar: _date_value(bar["date"]))
    first_index = next(
        (
            index
            for index, bar in enumerate(ordered)
            if _date_value(bar["date"]) >= _date_value(first_target)
        ),
        len(ordered),
    )
    start = max(0, first_index - max_prior_bars)
    return [
        bar
        for bar in ordered[start:]
        if _date_value(bar["date"]) <= _date_value(last_target)
    ]
