"""
Methods to handle connection to MongoDB
"""
from motor.motor_asyncio import AsyncIOMotorClient

from ..core.settings import MONGO_URI, MONGO_MAX_CONNECTIONS, MONGO_MIN_CONNECTIONS


class Database:  # pylint: disable=R0903
    """
    Class represeting Mongo databse
    """

    client: AsyncIOMotorClient = None


db = Database()


async def get_database() -> AsyncIOMotorClient:
    """
    Returns:
        AsyncIOMotorClient: return Mongo database object
    """
    return db.client


async def connect():
    """Connect to MongoDB"""
    db.client = AsyncIOMotorClient(
        str(MONGO_URI),
        maxPoolSize=MONGO_MAX_CONNECTIONS,
        minPoolSize=MONGO_MIN_CONNECTIONS,
    )
    print(f"Connected to mongo at {MONGO_URI}")


async def close():
    """Close MongoDB Connection"""
    db.client.close()
    print("Closed connection with MongoDB")
