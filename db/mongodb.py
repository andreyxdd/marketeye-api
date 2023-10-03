"""
Methods to handle connection to MongoDB
"""
from motor.motor_asyncio import AsyncIOMotorClient

from core.settings import MONGO_URI, MONGO_MAX_CONNECTIONS, MONGO_MIN_CONNECTIONS
import logging


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("DATABASE")


class MongoClient:
    """
    Class represeting Mongo database
    """
    client: AsyncIOMotorClient = None

    def connect(self):
        self.client = AsyncIOMotorClient(
            str(MONGO_URI),
            maxPoolSize=MONGO_MAX_CONNECTIONS,
            minPoolSize=MONGO_MIN_CONNECTIONS,
        )
        log.info(f"Connected to mongo at {MONGO_URI}")

    def get(self) -> AsyncIOMotorClient:
        if self.client:
            return self.client

        msg = "Database connection is not opened"
        log.error(msg)
        raise Exception(msg)

    def close(self):
        self.client.close()
        log.info("Closed connection with MongoDB")
