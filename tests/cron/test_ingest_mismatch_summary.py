"""Date-mismatch skips collapse into one summary line."""

import pytest

import services.analytics_service as analytics_service
import utils.handle_datetimes as handle_datetimes


@pytest.mark.asyncio
async def test_mismatched_tickers_logged_as_one_line(monkeypatch):
    tickers = [f"T{i}" for i in range(8)] + ["OK"]

    async def missing(conn, date, market):
        return tickers

    def fetch(ticker, date, market):
        return {"date": date if ticker == "OK" else "2026-11-24"}

    async def insert(conn, rows, batch_size):
        return len(rows)

    monkeypatch.setattr(analytics_service, "get_missing_tickers", missing)
    monkeypatch.setattr(analytics_service, "external_get_ticker_base_analytics", fetch)
    monkeypatch.setattr(analytics_service, "insert_analytics_batch", insert)
    monkeypatch.setattr(handle_datetimes, "bar_date_to_string", lambda d: d)

    msg = await analytics_service.ingest_base_analytics_for_market(None, "2026-11-25", "US")

    skipped = [line for line in msg.split("\n\n") if "skipped" in line]
    assert skipped == [
        "services/analytics_service: skipped 8 tickers for US — latest bar not on 2026-11-25:"
        " T0 (2026-11-24), T1 (2026-11-24), T2 (2026-11-24), T3 (2026-11-24),"
        " T4 (2026-11-24), +3 more"
    ]
    assert "computed 1 rows for US" in msg
