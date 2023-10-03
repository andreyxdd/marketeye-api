"""
Script to set and run the analytics cronjob.

Raises:
    Exception: If asyncio is not imported properly use trollius
"""

import logging
from time import time
from cronjob.cronjob import Cronjob

from db.mongodb import MongoClient


logging.basicConfig(level=logging.INFO)
log = logging.getLogger('CRONJOB SCRIPT')

try:
    import asyncio
except ImportError:
    import trollius as asyncio


async def job():
    try:
        mongoClient = MongoClient()
        mongoClient.connect()
        mongoDB = mongoClient.get()["basedb"]

        date = "2023-05-30"
        cronjob = Cronjob(mongoDB, date)
        await cronjob.run()

        mongoClient.connect()
    except Exception as e:  # pylint: disable=W0703
        log.error(e)


if __name__ == "__main__":
    try:
        log.info("Starting the cronjob ...")
        start_time = time()
        asyncio.run(job())
        log.info(
            "The cronjob finished in "
            +
            f"{round(time() - start_time, 2)} seconds"
        )
    except (KeyboardInterrupt, SystemExit):
        # Blocking execution when Ctrl+C (Ctrl+Break on Windows) is pressed
        pass
