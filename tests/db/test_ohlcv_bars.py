"""Unit tests for OHLCV bar store CRUD."""

from datetime import date, timedelta

import pytest

from db.crud.ohlcv_bars import (
    BarRow,
    delete_bars_for_session_date,
    fetch_bars,
    oldest_session_date,
    upsert_bars,
)
from db.ohlcv_sync import close_ohlcv_sync_pool


@pytest.fixture(autouse=True)
def _truncate_ohlcv_bars(postgres_pool):
    del postgres_pool
    from db.ohlcv_sync import get_ohlcv_sync_pool

    pool = get_ohlcv_sync_pool()
    if pool is not None:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE ohlcv_bars RESTART IDENTITY")
            conn.commit()
    yield


@pytest.fixture(autouse=True)
def _reset_ohlcv_sync_pool():
    close_ohlcv_sync_pool()
    yield
    close_ohlcv_sync_pool()


def _sample_rows(start: date, count: int) -> list[BarRow]:
    return [
        BarRow(
            session_date=start + timedelta(days=offset),
            open=100.0 + offset,
            high=101.0 + offset,
            low=99.0 + offset,
            close=100.5 + offset,
            volume=1_000_000 + offset,
        )
        for offset in range(count)
    ]


def test_upsert_idempotent_and_fetch_window(postgres_pool):
    del postgres_pool
    rows = _sample_rows(date(2024, 1, 1), 3)
    upsert_bars("US", "AAPL", rows)
    upsert_bars("US", "AAPL", rows)

    fetched = fetch_bars("US", "AAPL", date(2024, 1, 1), date(2024, 1, 3))
    assert len(fetched) == 3
    assert fetched[0].session_date == date(2024, 1, 3)
    assert fetched[-1].session_date == date(2024, 1, 1)


def test_upsert_overwrites_on_conflict(postgres_pool):
    del postgres_pool
    session = date(2024, 2, 1)
    upsert_bars(
        "US",
        "MSFT",
        [
            BarRow(
                session_date=session,
                open=1.0,
                high=2.0,
                low=0.5,
                close=1.5,
                volume=100,
            )
        ],
    )
    upsert_bars(
        "US",
        "MSFT",
        [
            BarRow(
                session_date=session,
                open=10.0,
                high=20.0,
                low=5.0,
                close=15.0,
                volume=200,
            )
        ],
    )

    fetched = fetch_bars("US", "MSFT", session, session)
    assert len(fetched) == 1
    assert fetched[0].close == 15.0
    assert fetched[0].volume == 200


def test_delete_bars_for_session_date(postgres_pool):
    del postgres_pool
    rows = _sample_rows(date(2024, 3, 1), 2)
    upsert_bars("US", "GOOGL", rows)
    deleted = delete_bars_for_session_date(date(2024, 3, 1))
    assert deleted >= 1

    remaining = fetch_bars("US", "GOOGL", date(2024, 3, 1), date(2024, 3, 2))
    assert len(remaining) == 1
    assert remaining[0].session_date == date(2024, 3, 2)


def test_oldest_session_date(postgres_pool):
    del postgres_pool
    assert oldest_session_date() is None

    upsert_bars("TO", "SHOP", _sample_rows(date(2024, 4, 10), 2))
    assert oldest_session_date() == date(2024, 4, 10)


def test_goog_normalizes_to_googl_ticker_key(postgres_pool):
    del postgres_pool
    session = date(2024, 5, 1)
    upsert_bars(
        "US",
        "GOOGL",
        [
            BarRow(
                session_date=session,
                open=1.0,
                high=2.0,
                low=0.5,
                close=1.5,
                volume=100,
            )
        ],
    )
    fetched = fetch_bars("US", "GOOGL", session, session)
    assert len(fetched) == 1
