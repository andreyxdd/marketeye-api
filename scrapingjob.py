"""
Script to set and run scraping cronjobs.
The idea is to scrape stock ticker
every trading day (often Monday to Friday)

Raises:
    Exception: If asyncio is not imported properly use trollius
"""

from time import time
from twisted.internet import reactor
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging
from scrapy.utils.project import get_project_settings
from utils.handle_emails import notify_developer
from utils.handle_datetimes import (
    get_today_utc_date_in_timezone,
    get_epoch,
)

from scraping.spiders.cnbc_spider import CNBCSpider
from scraping.spiders.cnn_spider import CNNSpider
from scraping.spiders.fool_spider import FoolSpider
from scraping.spiders.marketwatch_spider import MarketwatchSpider
from scraping.spiders.morningstar_spider import MorningstarSpider
from scraping.spiders.reuters_spider import ReutersSpider
from scraping.spiders.tipranks_spider import TipranksSpider
from scraping.spiders.yahoofinance_spider import YahoofinanceSpider

try:
    import asyncio
except ImportError:
    import trollius as asyncio


async def scrapingjob():
    """
    Function that defines the scrapingjob
    The functions also notifies developer about the results of the scrapingjob.
    """

    print("\n--------------------------------------------------------")
    print("Running scrapingjob ...\n")
    start_time = time()

    try:
        configure_logging()
        settings = get_project_settings()
        runner = CrawlerRunner(settings)
        runner.crawl(CNBCSpider)
        runner.crawl(CNNSpider)
        runner.crawl(FoolSpider)
        runner.crawl(MarketwatchSpider)
        runner.crawl(MorningstarSpider)
        runner.crawl(ReutersSpider)
        runner.crawl(TipranksSpider)
        runner.crawl(YahoofinanceSpider)
        dry = runner.join()
        dry.addBoth(lambda _: reactor.stop())

        reactor.run()

        notify_developer(
            body="Today scraping cronjob has completed successfully."
            + " Check MongoDB to see today scraping data"
        )
    except Exception as e:  # pylint: disable=W0703
        print("scrapingjob.py: Something went wrong.")
        print("Error message:", e)
        curr_date = get_today_utc_date_in_timezone("America/New_York")
        notify_developer(
            body=f"Scraping cronjob reported an error: {curr_date} ({get_epoch(curr_date)})"
            + f" with error message:\n\n {e}",
            subject="Scrapingjob Report",
        )

    print(f"\nScraping cronjob finished on {round(time() - start_time, 2)} seconds")
    print("--------------------------------------------------------")


if __name__ == "__main__":
    # Blocking execution when Ctrl+C (Ctrl+Break on Windows) is pressed
    try:
        asyncio.run(scrapingjob())  # initiating a cronjob
    except (KeyboardInterrupt, SystemExit):
        pass
