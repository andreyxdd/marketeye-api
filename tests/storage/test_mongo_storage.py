"""Unit tests for Mongo storage prune helpers."""

from datetime import date

import pytest

from core.settings import MONGO_DB_NAME
from db.crud import mongo_storage


@pytest.mark.asyncio
async def test_get_mongo_storage_ratio_sums_data_and_index_size(monkeypatch):
    class DbStub:
        async def command(self, name):
            assert name == "dbStats"
            # totalSize must be ignored — Atlas free/flex bills data+index only
            return {"dataSize": 256, "indexSize": 256, "totalSize": 999}

    conn = {MONGO_DB_NAME: DbStub()}
    size_bytes, ratio = await mongo_storage.get_mongo_storage_ratio(conn, 512)
    assert size_bytes == 512
    assert ratio == 1.0


@pytest.mark.asyncio
async def test_prune_mongo_session_date_deletes_analytics_and_tracking(monkeypatch):
    calls = []

    async def remove_stub(conn, date, collection_name="analytics", market="US"):
        del conn
        calls.append((date, collection_name, market))

    monkeypatch.setattr(mongo_storage, "remove_base_analytics", remove_stub)

    pruned = await mongo_storage.prune_mongo_session_date(
        object(), "2024-03-04", "US"
    )

    assert pruned is True
    assert ("2024-03-04", "analytics", "US") in calls
    assert ("2024-03-04", "tracking", "US") in calls


@pytest.mark.asyncio
async def test_prune_mongo_session_date_refuses_to_in_frequencies_lookback(
    monkeypatch,
):
    """TO date among last 40 published TO sessions → no analytics/tracking delete."""
    calls = []

    async def remove_stub(conn, date, collection_name="analytics", market="US"):
        del conn
        calls.append((date, collection_name, market))

    async def lookback_stub(pool, date):
        del pool
        assert date == "2024-06-03"
        return True

    monkeypatch.setattr(mongo_storage, "remove_base_analytics", remove_stub)
    monkeypatch.setattr(
        mongo_storage, "is_to_date_in_frequencies_lookback", lookback_stub
    )

    pruned = await mongo_storage.prune_mongo_session_date(
        object(), "2024-06-03", "TO", pool=object()
    )

    assert pruned is False
    assert calls == []


@pytest.mark.asyncio
async def test_prune_mongo_session_date_allows_to_outside_lookback(monkeypatch):
    calls = []

    async def remove_stub(conn, date, collection_name="analytics", market="US"):
        del conn
        calls.append((date, collection_name, market))

    async def lookback_stub(pool, date):
        del pool, date
        return False

    monkeypatch.setattr(mongo_storage, "remove_base_analytics", remove_stub)
    monkeypatch.setattr(
        mongo_storage, "is_to_date_in_frequencies_lookback", lookback_stub
    )

    pruned = await mongo_storage.prune_mongo_session_date(
        object(), "2024-01-02", "TO", pool=object()
    )

    assert pruned is True
    assert ("2024-01-02", "analytics", "TO") in calls
    assert ("2024-01-02", "tracking", "TO") in calls


@pytest.mark.asyncio
async def test_prune_mongo_if_published_only_when_published(monkeypatch):
    calls = {"pruned": 0}

    async def published_stub(pool, date, market):
        del pool, date, market
        return False

    async def prune_stub(conn, date, market, pool=None):
        del conn, date, market, pool
        calls["pruned"] += 1
        return True

    monkeypatch.setattr(mongo_storage, "is_archive_complete", published_stub)
    monkeypatch.setattr(mongo_storage, "prune_mongo_session_date", prune_stub)

    result = await mongo_storage.prune_mongo_if_published(object(), object(), "2024-03-04", "US")
    assert result is False
    assert calls["pruned"] == 0

    async def published_true_stub(pool, date, market):
        del pool, date, market
        return True

    monkeypatch.setattr(mongo_storage, "is_archive_complete", published_true_stub)

    result = await mongo_storage.prune_mongo_if_published(object(), object(), "2024-03-04", "US")
    assert result is True
    assert calls["pruned"] == 1


@pytest.mark.asyncio
async def test_is_to_date_in_frequencies_lookback_uses_last_40(monkeypatch):
    """Independent fixture: 41 TO dates DESC → only newest 40 protected."""
    # 2024-01-01 .. 2024-02-10 = 41 calendar days used as stand-in trading days
    rows = [
        {"session_date": date(2024, 1, 1) + __import__("datetime").timedelta(days=i)}
        for i in range(41)
    ]
    # Postgres ORDER BY DESC returns newest first
    rows_desc = list(reversed(rows))
    fetch_args = []

    class PgConnStub:
        async def fetch(self, query, *args):
            fetch_args.append((query, args))
            return rows_desc[: args[1]]  # LIMIT $2

    class PoolStub:
        def acquire(self):
            return self

        async def __aenter__(self):
            return PgConnStub()

        async def __aexit__(self, *args):
            del args

    assert await mongo_storage.is_to_date_in_frequencies_lookback(
        PoolStub(), "2024-02-10"
    )
    assert await mongo_storage.is_to_date_in_frequencies_lookback(
        PoolStub(), "2024-01-02"
    )
    assert not await mongo_storage.is_to_date_in_frequencies_lookback(
        PoolStub(), "2024-01-01"
    )
    assert fetch_args
    assert "TO" in fetch_args[0][1][0] or fetch_args[0][1][0] == "TO"
    assert fetch_args[0][1][1] == mongo_storage.TO_FREQUENCIES_LOOKBACK_TRADING_DAYS


@pytest.mark.asyncio
async def test_prune_oldest_published_mongo_session_all_markets(monkeypatch):
    calls = []

    class PgConnStub:
        async def fetchrow(self, query, *args):
            del query, args
            return {"session_date": __import__("datetime").date(2024, 1, 2)}

    class PoolStub:
        def acquire(self):
            return self

        async def __aenter__(self):
            return PgConnStub()

        async def __aexit__(self, *args):
            del args

    async def prune_session_stub(conn, date, market, pool=None):
        del conn, pool
        calls.append((date, market))
        return True

    monkeypatch.setattr(mongo_storage, "list_markets", lambda: ["US", "TO"])
    async def archive_complete_stub(pool, date, market):
        del pool, date, market
        return True

    monkeypatch.setattr(mongo_storage, "is_archive_complete", archive_complete_stub)
    monkeypatch.setattr(mongo_storage, "prune_mongo_session_date", prune_session_stub)

    result = await mongo_storage.prune_oldest_published_mongo_session(PoolStub(), object())
    assert result == "2024-01-02"
    assert calls == [("2024-01-02", "US"), ("2024-01-02", "TO")]


@pytest.mark.asyncio
async def test_prune_oldest_skips_to_inside_frequencies_lookback(monkeypatch):
    """US still pruned; TO analytics/tracking kept when date is in lookback."""
    remove_calls = []

    class PgConnStub:
        async def fetchrow(self, query, *args):
            del query, args
            return {"session_date": date(2024, 6, 3)}

    class PoolStub:
        def acquire(self):
            return self

        async def __aenter__(self):
            return PgConnStub()

        async def __aexit__(self, *args):
            del args

    async def remove_stub(conn, date, collection_name="analytics", market="US"):
        del conn
        remove_calls.append((date, collection_name, market))

    async def lookback_stub(pool, date):
        del pool
        return date == "2024-06-03"

    async def archive_complete_stub(pool, date, market):
        del pool, date, market
        return True

    monkeypatch.setattr(mongo_storage, "list_markets", lambda: ["US", "TO"])
    monkeypatch.setattr(mongo_storage, "is_archive_complete", archive_complete_stub)
    monkeypatch.setattr(mongo_storage, "remove_base_analytics", remove_stub)
    monkeypatch.setattr(
        mongo_storage, "is_to_date_in_frequencies_lookback", lookback_stub
    )

    result = await mongo_storage.prune_oldest_published_mongo_session(
        PoolStub(), object()
    )
    assert result == "2024-06-03"
    assert ("2024-06-03", "analytics", "US") in remove_calls
    assert ("2024-06-03", "tracking", "US") in remove_calls
    assert not any(market == "TO" for _, _, market in remove_calls)


@pytest.mark.asyncio
async def test_prune_oldest_skips_exclude_dates(monkeypatch):
    """Oldest published date in exclude set → pick next oldest."""
    fetch_args = []

    class PgConnStub:
        async def fetchrow(self, query, *args):
            fetch_args.append((query, args))
            assert "<> ALL" in query or "NOT IN" in query.upper() or "= ANY" in query
            return {"session_date": __import__("datetime").date(2024, 1, 3)}

    class PoolStub:
        def acquire(self):
            return self

        async def __aenter__(self):
            return PgConnStub()

        async def __aexit__(self, *args):
            del args

    async def prune_session_stub(conn, date, market, pool=None):
        del conn, date, market, pool

    monkeypatch.setattr(mongo_storage, "list_markets", lambda: ["US"])
    async def archive_complete_stub(pool, date, market):
        del pool, date, market
        return True

    monkeypatch.setattr(mongo_storage, "is_archive_complete", archive_complete_stub)
    monkeypatch.setattr(mongo_storage, "prune_mongo_session_date", prune_session_stub)

    result = await mongo_storage.prune_oldest_published_mongo_session(
        PoolStub(),
        object(),
        exclude_dates=["2024-01-02"],
    )
    assert result == "2024-01-03"
    assert fetch_args
    bound_exclude = fetch_args[0][1][0]
    assert bound_exclude == [date(2024, 1, 2)]
    assert all(isinstance(d, date) for d in bound_exclude)
    assert not any(isinstance(d, str) for d in bound_exclude)


@pytest.mark.asyncio
async def test_prune_oldest_returns_none_when_all_excluded(monkeypatch):
    class PgConnStub:
        async def fetchrow(self, query, *args):
            del query, args
            return None

    class PoolStub:
        def acquire(self):
            return self

        async def __aenter__(self):
            return PgConnStub()

        async def __aexit__(self, *args):
            del args

    async def prune_session_stub(conn, date, market, pool=None):
        del conn, date, market, pool
        raise AssertionError("must not prune when no date left")

    monkeypatch.setattr(mongo_storage, "list_markets", lambda: ["US"])
    async def archive_complete_stub(pool, date, market):
        del pool, date, market
        return True

    monkeypatch.setattr(mongo_storage, "is_archive_complete", archive_complete_stub)
    monkeypatch.setattr(mongo_storage, "prune_mongo_session_date", prune_session_stub)

    result = await mongo_storage.prune_oldest_published_mongo_session(
        PoolStub(),
        object(),
        exclude_dates=["2024-01-01", "2024-01-02"],
    )
    assert result is None
