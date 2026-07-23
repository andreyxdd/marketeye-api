"""Unit tests for band-tracking backfill script."""

import pytest

import scripts.backfill_band_tracking as backfill_band_tracking


def _patch_connections(monkeypatch):
    monkeypatch.setattr(
        backfill_band_tracking, "connect_mongo", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "close_mongo", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "connect_postgres", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "close_postgres", lambda: _async_noop()
    )
    monkeypatch.setattr(
        backfill_band_tracking, "get_mongo_database", lambda: _async_return(object())
    )
    monkeypatch.setattr(
        backfill_band_tracking, "get_postgres_pool", lambda: _async_return(object())
    )


@pytest.mark.asyncio
async def test_dry_run_calls_neither_put_nor_publish(monkeypatch, capsys):
    calls = []

    async def fake_get_published_dates(pool, market="US"):
        del pool
        return [{"date_string": "2024-06-01"}, {"date_string": "2024-06-03"}]

    async def fake_analytics_exist(conn, date, market):
        del conn
        return True

    async def fake_put(conn, date, market="US"):
        calls.append(("put", date, market))
        return "put"

    async def fake_publish(conn, pool, date, market="US", include_mentions=False):
        calls.append(("publish", date, market, include_mentions))
        return {"artifacts": 1, "tickers": 1}

    async def fake_patch(conn, pool, date, market="US"):
        calls.append(("patch", date, market))
        return 1

    monkeypatch.setattr(
        backfill_band_tracking, "get_published_dates", fake_get_published_dates
    )
    monkeypatch.setattr(
        backfill_band_tracking, "analytics_exist", fake_analytics_exist
    )
    monkeypatch.setattr(backfill_band_tracking, "put_top_tickers", fake_put)
    monkeypatch.setattr(backfill_band_tracking, "publish_day", fake_publish)
    monkeypatch.setattr(
        backfill_band_tracking, "patch_day_frequencies", fake_patch
    )
    _patch_connections(monkeypatch)

    await backfill_band_tracking.run_backfill(
        markets=["US"], trading_days=15, dry_run=True
    )

    assert calls == []
    out = capsys.readouterr().out
    assert "2024-06-01" in out
    assert "2024-06-03" in out
    assert "dry-run" in out.lower() or "DRY" in out


@pytest.mark.asyncio
async def test_apply_calls_put_then_patch_not_publish(monkeypatch):
    calls = []

    async def fake_get_published_dates(pool, market="US"):
        del pool
        return [
            {"date_string": "2024-05-01"},
            {"date_string": "2024-06-01"},
            {"date_string": "2024-06-03"},
        ]

    async def fake_analytics_exist(conn, date, market):
        del conn, market
        return date in {"2024-06-01", "2024-06-03"}

    async def fake_put(conn, date, market="US"):
        calls.append(("put", date, market))
        return "put"

    async def fake_publish(conn, pool, date, market="US", include_mentions=False):
        calls.append(("publish", date, market))
        return {"artifacts": 1, "tickers": 1}

    async def fake_patch(conn, pool, date, market="US"):
        calls.append(("patch", date, market))
        return 2

    monkeypatch.setattr(
        backfill_band_tracking, "get_published_dates", fake_get_published_dates
    )
    monkeypatch.setattr(
        backfill_band_tracking, "analytics_exist", fake_analytics_exist
    )
    monkeypatch.setattr(backfill_band_tracking, "put_top_tickers", fake_put)
    monkeypatch.setattr(backfill_band_tracking, "publish_day", fake_publish)
    monkeypatch.setattr(
        backfill_band_tracking, "patch_day_frequencies", fake_patch
    )
    _patch_connections(monkeypatch)

    await backfill_band_tracking.run_backfill(
        markets=["US"], trading_days=2, dry_run=False
    )

    assert calls == [
        ("put", "2024-06-01", "US"),
        ("patch", "2024-06-01", "US"),
        ("put", "2024-06-03", "US"),
        ("patch", "2024-06-03", "US"),
    ]
    assert not any(c[0] == "publish" for c in calls)


@pytest.mark.asyncio
async def test_full_publish_calls_publish_day(monkeypatch):
    calls = []

    async def fake_get_published_dates(pool, market="US"):
        del pool
        return [{"date_string": "2024-06-01"}]

    async def fake_analytics_exist(conn, date, market):
        del conn, market, date
        return True

    async def fake_put(conn, date, market="US"):
        calls.append(("put", date, market))
        return "put"

    async def fake_publish(conn, pool, date, market="US", include_mentions=False):
        calls.append(("publish", date, market, include_mentions))
        return {"artifacts": 1, "tickers": 1}

    async def fake_patch(conn, pool, date, market="US"):
        calls.append(("patch", date, market))
        return 1

    monkeypatch.setattr(
        backfill_band_tracking, "get_published_dates", fake_get_published_dates
    )
    monkeypatch.setattr(
        backfill_band_tracking, "analytics_exist", fake_analytics_exist
    )
    monkeypatch.setattr(backfill_band_tracking, "put_top_tickers", fake_put)
    monkeypatch.setattr(backfill_band_tracking, "publish_day", fake_publish)
    monkeypatch.setattr(
        backfill_band_tracking, "patch_day_frequencies", fake_patch
    )
    _patch_connections(monkeypatch)

    await backfill_band_tracking.run_backfill(
        markets=["US"], trading_days=15, dry_run=False, full_publish=True
    )

    assert calls == [
        ("put", "2024-06-01", "US"),
        ("publish", "2024-06-01", "US", False),
    ]
    assert not any(c[0] == "patch" for c in calls)


@pytest.mark.asyncio
async def test_patch_day_frequencies_upserts_lists_and_criterion(monkeypatch):
    upserts = []
    freq_calls = []

    async def fake_get_artifact(pool, date, artifact_key, market="US"):
        del pool, market
        if artifact_key == "lists_by_criteria:all":
            return {
                "by_one_day_avg_mf": [{"ticker": "AAA", "frequencies": "old"}],
                "by_three_day_avg_mf": [],
                "by_volume": [],
                "by_three_day_avg_volume": [],
                "by_macd": [],
            }
        if artifact_key == "lists_by_criterion:one_day_avg_mf:all":
            return {"one_day_avg_mf": [{"ticker": "AAA", "frequencies": "old"}]}
        return None

    async def fake_upsert(pool, date, artifact_key, payload, market="US"):
        upserts.append((artifact_key, payload, market, date))

    async def fake_freqs(
        conn, date, criterion, ticker, market="US", price_band=None, period=25
    ):
        del conn, period
        freq_calls.append((date, criterion, ticker, market, price_band))
        return "T-1"

    monkeypatch.setattr(
        backfill_band_tracking, "get_artifact_payload", fake_get_artifact
    )
    monkeypatch.setattr(backfill_band_tracking, "upsert_artifact", fake_upsert)
    monkeypatch.setattr(
        backfill_band_tracking, "get_analytics_frequencies", fake_freqs
    )
    # Limit bands/criteria so test stays small
    monkeypatch.setattr(
        backfill_band_tracking, "PRICE_BANDS_TO_PUBLISH", [None]
    )
    monkeypatch.setattr(backfill_band_tracking, "CRITERIA", ["one_day_avg_mf"])

    written = await backfill_band_tracking.patch_day_frequencies(
        object(), object(), "2024-06-01", market="US"
    )

    assert written >= 1
    assert ("2024-06-01", "one_day_avg_mf", "AAA", "US", None) in freq_calls

    lists_upsert = next(u for u in upserts if u[0] == "lists_by_criteria:all")
    assert lists_upsert[1]["by_one_day_avg_mf"][0]["frequencies"] == "T-1"

    crit_upsert = next(
        u for u in upserts if u[0] == "lists_by_criterion:one_day_avg_mf:all"
    )
    assert crit_upsert[1]["one_day_avg_mf"][0]["frequencies"] == "T-1"


@pytest.mark.asyncio
async def test_patch_skips_missing_artifacts(monkeypatch, capsys):
    upserts = []

    async def fake_get_artifact(pool, date, artifact_key, market="US"):
        del pool, date, artifact_key, market
        return None

    async def fake_upsert(*args, **kwargs):
        upserts.append((args, kwargs))

    async def fake_freqs(*args, **kwargs):
        raise AssertionError("get_analytics_frequencies must not run when missing")

    monkeypatch.setattr(
        backfill_band_tracking, "get_artifact_payload", fake_get_artifact
    )
    monkeypatch.setattr(backfill_band_tracking, "upsert_artifact", fake_upsert)
    monkeypatch.setattr(
        backfill_band_tracking, "get_analytics_frequencies", fake_freqs
    )
    monkeypatch.setattr(
        backfill_band_tracking, "PRICE_BANDS_TO_PUBLISH", [None]
    )
    monkeypatch.setattr(backfill_band_tracking, "CRITERIA", ["one_day_avg_mf"])

    written = await backfill_band_tracking.patch_day_frequencies(
        object(), object(), "2024-06-01", market="US"
    )

    assert written == 0
    assert upserts == []
    out = capsys.readouterr().out.lower()
    assert "skip" in out


@pytest.mark.asyncio
async def test_skips_dates_without_analytics(monkeypatch, capsys):
    calls = []

    async def fake_get_published_dates(pool, market="US"):
        del pool
        return [{"date_string": "2024-06-01"}, {"date_string": "2024-06-03"}]

    async def fake_analytics_exist(conn, date, market):
        del conn, market
        return date == "2024-06-03"

    async def fake_put(conn, date, market="US"):
        calls.append(("put", date, market))
        return "put"

    async def fake_publish(conn, pool, date, market="US", include_mentions=False):
        calls.append(("publish", date, market))
        return {"artifacts": 1, "tickers": 1}

    async def fake_patch(conn, pool, date, market="US"):
        calls.append(("patch", date, market))
        return 1

    monkeypatch.setattr(
        backfill_band_tracking, "get_published_dates", fake_get_published_dates
    )
    monkeypatch.setattr(
        backfill_band_tracking, "analytics_exist", fake_analytics_exist
    )
    monkeypatch.setattr(backfill_band_tracking, "put_top_tickers", fake_put)
    monkeypatch.setattr(backfill_band_tracking, "publish_day", fake_publish)
    monkeypatch.setattr(
        backfill_band_tracking, "patch_day_frequencies", fake_patch
    )
    _patch_connections(monkeypatch)

    await backfill_band_tracking.run_backfill(
        markets=["US"], trading_days=15, dry_run=False
    )

    assert calls == [
        ("put", "2024-06-03", "US"),
        ("patch", "2024-06-03", "US"),
    ]
    out = capsys.readouterr().out
    assert "2024-06-01" in out
    assert "skip" in out.lower()


def test_parse_markets_default_and_normalize():
    assert backfill_band_tracking.parse_markets("US,TO") == ["US", "TO"]
    assert backfill_band_tracking.parse_markets("us, to") == ["US", "TO"]


def test_parser_full_publish_default_off():
    parser = backfill_band_tracking.build_parser()
    args = parser.parse_args([])
    assert args.full_publish is False
    args_on = parser.parse_args(["--full-publish"])
    assert args_on.full_publish is True


async def _async_noop():
    return None


async def _async_return(value):
    return value
