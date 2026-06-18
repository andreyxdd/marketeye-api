"""Unit tests for Mongo storage prune helpers."""

import pytest

from core.settings import MONGO_DB_NAME
from db.crud import mongo_storage


@pytest.mark.asyncio
async def test_get_mongo_storage_ratio_uses_data_size(monkeypatch):
    class DbStub:
        async def command(self, name):
            assert name == "dbStats"
            return {"dataSize": 256, "totalSize": 512}

    conn = {MONGO_DB_NAME: DbStub()}
    size_bytes, ratio = await mongo_storage.get_mongo_storage_ratio(conn, 512)
    assert size_bytes == 256
    assert ratio == 0.5


@pytest.mark.asyncio
async def test_prune_mongo_session_date_deletes_analytics_and_tracking(monkeypatch):
    calls = []

    async def remove_stub(conn, date, collection_name="analytics", market="US"):
        del conn
        calls.append((date, collection_name, market))

    monkeypatch.setattr(mongo_storage, "remove_base_analytics", remove_stub)

    await mongo_storage.prune_mongo_session_date(object(), "2024-03-04", "US")

    assert ("2024-03-04", "analytics", "US") in calls
    assert ("2024-03-04", "tracking", "US") in calls


@pytest.mark.asyncio
async def test_prune_mongo_if_published_only_when_published(monkeypatch):
    calls = {"pruned": 0}

    async def published_stub(pool, date, market):
        del pool, date, market
        return False

    async def prune_stub(conn, date, market):
        del conn, date, market
        calls["pruned"] += 1

    monkeypatch.setattr(mongo_storage, "is_session_published", published_stub)
    monkeypatch.setattr(mongo_storage, "prune_mongo_session_date", prune_stub)

    result = await mongo_storage.prune_mongo_if_published(object(), object(), "2024-03-04", "US")
    assert result is False
    assert calls["pruned"] == 0

    async def published_true_stub(pool, date, market):
        del pool, date, market
        return True

    monkeypatch.setattr(mongo_storage, "is_session_published", published_true_stub)

    result = await mongo_storage.prune_mongo_if_published(object(), object(), "2024-03-04", "US")
    assert result is True
    assert calls["pruned"] == 1


@pytest.mark.asyncio
async def test_prune_oldest_published_mongo_session_all_markets(monkeypatch):
    calls = []

    class PgConnStub:
        async def fetchrow(self, query):
            del query
            return {"session_date": __import__("datetime").date(2024, 1, 2)}

    class PoolStub:
        def acquire(self):
            return self

        async def __aenter__(self):
            return PgConnStub()

        async def __aexit__(self, *args):
            del args

    async def prune_session_stub(conn, date, market):
        del conn
        calls.append((date, market))

    monkeypatch.setattr(mongo_storage, "list_markets", lambda: ["US", "TO"])
    monkeypatch.setattr(mongo_storage, "prune_mongo_session_date", prune_session_stub)

    result = await mongo_storage.prune_oldest_published_mongo_session(PoolStub(), object())
    assert result == "2024-01-02"
    assert calls == [("2024-01-02", "US"), ("2024-01-02", "TO")]
