"""Root pytest configuration and shared session fixtures."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load secrets from .env, then force local test infra before settings/db import.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)
os.environ["MONGO_URI"] = "mongodb://localhost:27017"
os.environ["REDIS_URI"] = "redis://localhost:6379/1"
os.environ["MONGO_DB_NAME"] = "marketeye_test"
os.environ["DATABASE_URL"] = "postgresql://marketeye:marketeye@localhost:5432/marketeye_test"

from tests.helpers.constants import FIXTURE_API_KEY

os.environ["API_KEY"] = FIXTURE_API_KEY

import pytest
import pytest_asyncio

from db.mongodb import close as close_mongo
from db.mongodb import connect as connect_mongo
from db.mongodb import db
from db.postgres import close as close_postgres
from db.postgres import connect as connect_postgres
from db.postgres import get_pool as get_postgres_pool
from db.crud.published_archive import truncate_published_tables
from scripts.apply_migrations import apply_migrations
from db.redis import RedisCache
from tests.helpers.seed import seed_collections


def pytest_configure(config):
    pass


@pytest.fixture(scope="session")
def fixture_date():
    from tests.helpers.constants import FIXTURE_DATE

    return FIXTURE_DATE


@pytest.fixture(scope="session")
def fixture_api_key():
    return FIXTURE_API_KEY


@pytest.fixture(autouse=True)
def _clear_ticker_universe_cache():
    from utils.handle_external_apis import clear_ticker_universe_cache

    clear_ticker_universe_cache()
    yield
    clear_ticker_universe_cache()


@pytest_asyncio.fixture(scope="session")
async def postgres_pool():
    await connect_postgres()
    await apply_migrations()
    pool = await get_postgres_pool()
    await truncate_published_tables(pool)
    yield pool
    await close_postgres()


@pytest_asyncio.fixture(scope="session")
async def mongo_client(postgres_pool):  # pylint: disable=unused-argument
    await connect_mongo()
    cache = RedisCache()
    cache.connect()
    if cache.client:
        cache.client.flushdb()
    await seed_collections(db.client)
    yield db.client
    await close_mongo()
