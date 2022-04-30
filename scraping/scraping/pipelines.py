"""
Scrapy pipeline to handle each output from a spider
"""
import pymongo
from core.settings import MONGO_URI, MONGO_DB_NAME
from utils.handle_datetimes import get_epoch


MONGO_COLLECTION_NAME = "analytics"


class MongoPipeline:
    """
    A class to handle the pipeline base on pymongo
    """

    epoch_date = get_epoch("2022-02-01")
    db_tickers = []

    def __init__(self):
        self.client = pymongo.MongoClient(MONGO_URI)
        self.db = self.client[MONGO_DB_NAME]

    def open_spider(self):
        """
        Method to handle the spider start up
        """
        try:
            cursor = self.db[MONGO_COLLECTION_NAME].distinct(
                "ticker", {"date": self.epoch_date}
            )
            self.db_tickers = list(cursor)
        except Exception as e:
            print("Error message:", e)
            raise Exception(
                "scraping/scraping/pipe;ines.py, def open_spider reported an error"
            ) from e

    def close_spider(self):
        """
        Method to handle the spider compleition
        """
        self.client.close()

    def process_item(self, item):
        """
        Processing the item by incrementing the mentions count
        if a given ticker is in the list of ticker for the current date
        """

        for ticker in item["tickers"]:
            if ticker in self.db_tickers:
                self.db[MONGO_COLLECTION_NAME].update_one(
                    {"ticker": ticker, "date": self.epoch_date},
                    {"$inc": {"mentions": 1}},
                )

        return item
