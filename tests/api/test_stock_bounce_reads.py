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
