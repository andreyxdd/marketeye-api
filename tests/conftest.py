"""Root pytest configuration and shared session fixtures."""

import os

import pytest
import pytest_asyncio

from db.mongodb import close as close_mongo
from db.mongodb import connect as connect_mongo
from db.mongodb import db
from db.redis import RedisCache
from tests.helpers.constants import FIXTURE_API_KEY
from tests.helpers.seed import seed_collections


def pytest_configure(config):
    os.environ.setdefault("API_KEY", FIXTURE_API_KEY)
    os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
    os.environ.setdefault("REDIS_URI", "redis://localhost:6379/1")
    os.environ.setdefault("MONGO_DB_NAME", "marketeye_test")
    os.environ.setdefault("POLYGON_API_KEY", "test-polygon-key")


@pytest.fixture(scope="session")
def fixture_date():
    from tests.helpers.constants import FIXTURE_DATE

    return FIXTURE_DATE


@pytest.fixture(scope="session")
def fixture_api_key():
    return FIXTURE_API_KEY


@pytest_asyncio.fixture(scope="session")
async def mongo_client():
    await connect_mongo()
    cache = RedisCache()
    cache.connect()
    if cache.client:
        cache.client.flushdb()
    await seed_collections(db.client)
    yield db.client
    await close_mongo()
