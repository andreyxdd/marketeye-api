"""Validation-aware, bounded StockBounce archive reads."""

import base64
from datetime import date, timedelta

import pytest

from services.stock_bounce import reads


def _snapshot(date_string):
    return {
        "schema_version": 1,
        "market": "US",
        "date": date_string,
        "rows": [
            {
                "ticker": "ABC",
                "open": 100.0,
                "close": 105.0,
                "volume": 1000,
                "open_close_change_pct": 5.0,
                "bounce": [0.0] * 18,
            }
        ],
        "coverage": {
            "status": "exact",
            "universe_provenance": "fixture",
            "declared_universe_count": 1,
            "row_count": 1,
            "exclusions": [],
        },
    }


class FakeConnection:
    def __init__(self, records):
        self.records = records
        self.limits = []

    async def fetch(self, query, artifact_key, after, batch_size):
        del query, artifact_key
        self.limits.append(batch_size)
        remaining = [
            record
            for record in self.records
            if after is None or record["session_date"] > after
        ]
        return remaining[:batch_size]


class FakePool:
    def __init__(self, records):
        self.connection = FakeConnection(records)

    def acquire(self):
        pool = self

        class Acquisition:
            async def __aenter__(self):
                return pool.connection

            async def __aexit__(self, *args):
                del args

        return Acquisition()


@pytest.mark.asyncio
async def test_sessions_fetch_bounded_batches_and_skip_trailing_invalid_artifacts(
    monkeypatch,
):
    start = date(2024, 1, 1)
    records = []
    for index in range(15):
        date_string = (start + timedelta(days=index)).isoformat()
        payload = _snapshot(date_string) if index in (0, 10, 11, 14) else {}
        records.append({"session_date": start + timedelta(days=index), "payload": payload})
    pool = FakePool(records)
    validated = []
    original_validate = reads.validate_snapshot

    def counted_validate(snapshot):
        validated.append(snapshot)
        return original_validate(snapshot)

    monkeypatch.setattr(reads, "validate_snapshot", counted_validate)

    result = await reads.list_sessions(pool, limit=2)

    assert [item["date_string"] for item in result["items"]] == [
        "2024-01-01",
        "2024-01-11",
    ]
    cursor = result["next_cursor"]
    padding = "=" * (-len(cursor) % 4)
    assert base64.urlsafe_b64decode(cursor + padding).decode("ascii") == "2024-01-11"
    assert pool.connection.limits == [10, 10]
    assert len(validated) == 12
    assert _snapshot("2024-01-15") not in validated


def _decode_cursor(cursor):
    padding = "=" * (-len(cursor) % 4)
    return base64.urlsafe_b64decode(cursor + padding).decode("ascii")


def _records(valid_indexes, count=25):
    start = date(2024, 1, 1)
    return [
        {
            "session_date": start + timedelta(days=index),
            "payload": (
                _snapshot((start + timedelta(days=index)).isoformat())
                if index in valid_indexes
                else {}
            ),
        }
        for index in range(count)
    ]


@pytest.mark.asyncio
async def test_scan_budget_returns_empty_resumable_pages_then_normal_exhaustion(
    monkeypatch,
):
    monkeypatch.setattr(reads, "SCAN_ROW_BUDGET", 10)
    pool = FakePool(_records(set()))
    validated = []
    original_validate = reads.validate_snapshot

    def counted_validate(snapshot):
        validated.append(snapshot)
        return original_validate(snapshot)

    monkeypatch.setattr(reads, "validate_snapshot", counted_validate)

    first = await reads.list_sessions(pool, limit=2)
    assert first["items"] == []
    assert _decode_cursor(first["next_cursor"]) == "2024-01-10"
    assert len(validated) == 10

    second = await reads.list_sessions(pool, cursor=first["next_cursor"], limit=2)
    assert second["items"] == []
    assert _decode_cursor(second["next_cursor"]) == "2024-01-20"
    assert len(validated) == 20

    third = await reads.list_sessions(pool, cursor=second["next_cursor"], limit=2)
    assert third == {"items": [], "next_cursor": None}
    assert len(validated) == 25
    assert pool.connection.limits == [10, 10, 10]


@pytest.mark.asyncio
async def test_scan_budget_cursor_resumes_after_scanned_rows_without_gaps(
    monkeypatch,
):
    monkeypatch.setattr(reads, "SCAN_ROW_BUDGET", 10)
    pool = FakePool(_records({0, 9, 10, 11, 20}))

    first = await reads.list_sessions(pool, limit=2)
    assert [item["date_string"] for item in first["items"]] == [
        "2024-01-01",
        "2024-01-10",
    ]
    assert _decode_cursor(first["next_cursor"]) == "2024-01-10"

    second = await reads.list_sessions(pool, cursor=first["next_cursor"], limit=2)
    assert [item["date_string"] for item in second["items"]] == [
        "2024-01-11",
        "2024-01-12",
    ]
    assert _decode_cursor(second["next_cursor"]) == "2024-01-20"

    third = await reads.list_sessions(pool, cursor=second["next_cursor"], limit=2)
    assert [item["date_string"] for item in third["items"]] == ["2024-01-21"]
    assert third["next_cursor"] is None
