"""
Scrapy pipeline to handle each output from a spider
"""
import pymongo
from core.settings import MONGO_URI, MONGO_DB_NAME, DATE_TO_SCRAPE
from utils.handle_datetimes import (
    get_epoch,
    get_past_date,
    get_today_utc_date_in_timezone,
)
from utils.handle_external_apis import get_quandl_tickers

MONGO_COLLECTION_NAME = "scrapes"


class MongoPipeline:
    """
    A class to handle the pipeline base on pymongo
    """

    date = (
        DATE_TO_SCRAPE
        if DATE_TO_SCRAPE
        else get_today_utc_date_in_timezone("America/New_York")
    )
    quandl_tickers = []

    def __init__(self):
        self.client = pymongo.MongoClient(MONGO_URI)
        self.db = self.client[MONGO_DB_NAME]

    def open_spider(self, spider):  # pylint: disable=W0613
        """
        Method to handle the spider start up
        """

        curr_date = self.date
        while True:
            self.quandl_tickers = get_quandl_tickers(curr_date)

            if len(self.quandl_tickers) > 0:
                break

            curr_date = get_past_date(1, self.date)

    def close_spider(self, spider):  # pylint: disable=W0613
        """
        Method to handle the spider compleition
        """
        self.client.close()

    def process_item(self, item, spider):  # pylint: disable=W0613
        """
        Processing the item by incrementing the mentions count
        if a given ticker is in the list of ticker for the current date
        """

        try:
            for ticker in item["tickers"]:
                if ticker in self.quandl_tickers:
                    self.db[MONGO_COLLECTION_NAME].update_one(
                        {
                            "ticker": ticker,
                            "date": get_epoch(self.date),
                        },
                        {"$inc": {"mentions": 1}},
                        upsert=True,
                    )

        except Exception as e:
            print("Error message:", e)
            raise Exception(
                "scraping/scraping/pipe;ines.py, def process_item reported an error"
            ) from e

        return item
