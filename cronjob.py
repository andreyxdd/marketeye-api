"""
Script to set and run analytics-computing and scraping cronjobs.
The idea is to compute and insert stocks analytics and
scraping every trading day (often Monday to Friday)

Raises:
    Exception: If asyncio is not imported properly use trollius
"""

from time import time
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from db.mongodb import connect, get_database, close
from db.crud.analytics import compute_base_analytics_and_insert, remove_base_analytics
from utils.handle_emails import notify_developer
from utils.handle_datetimes import (
    get_today_utc_date_in_timezone,
    get_past_date,
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


async def run_crud_ops(date_to_insert: str, date_to_remove: str) -> str:
    """
    Method to run certain crud operations on the analytics collection.

    Args:
        date_to_insert (str):
            date, for which new base analytics is computed and inserted into db
        date_to_remove (str):
            date, for which old base analytics is removed from db
    """

    # connecting mongo db and getting its connection string
    await connect()
    conn = await get_database()

    msg = await compute_base_analytics_and_insert(conn, date_to_insert)

    await remove_base_analytics(conn, date_to_remove)

    # disconneting mongo db
    await close()

    return msg


async def cronjob():
    """
    Function that defines the cronjob:
        - first, todays date is found (in NY time zone with respect to UTC)
        - then, past date (3 month ago) is found
        - next, the crud operations are run for the above dates.

    The functions also notifies developer about the results of the cronjob.
    """

    print("\n--------------------------------------------------------")
    print("Running analytics cronjob ...\n")
    start_time = time()

    try:
        curr_date = get_today_utc_date_in_timezone("America/New_York")
        past_date = get_past_date(91, curr_date)
        msg = await run_crud_ops(curr_date, past_date)

    except Exception as e:  # pylint: disable=W0703
        print("cronjob.py: Something went wrong.")
        print("Error message:", e)
        notify_developer(
            body=f"Analytics cronjob reported an error: {curr_date} ({get_epoch(curr_date)})"
            + f" with rror message:\n\n {e}",
            subject="Cronjob Report",
        )

    notify_developer(
        body="Today analytics cronjob has completed successfully."
        + " Check MongoDB to see if today base analytics data"
        + f", {curr_date} ({get_epoch(curr_date)}), was inserted."
        + "\n\n----------------------- Logs ---------------------------\n\n"
        + f"{msg}"
        + "\n\n--------------------------------------------------------"
    )

    print(f"\nAnalytics cronjob finished on {round(time() - start_time, 2)} seconds")
    print("--------------------------------------------------------")

    print("\n--------------------------------------------------------")
    print("Running scraping cronjob ...\n")
    start_time = time()

    try:
        process = CrawlerProcess(get_project_settings())
        process.crawl(CNBCSpider)
        process.crawl(CNNSpider)
        process.crawl(FoolSpider)
        process.crawl(MarketwatchSpider)
        process.crawl(MorningstarSpider)
        process.crawl(ReutersSpider)
        process.crawl(TipranksSpider)
        process.crawl(YahoofinanceSpider)
        process.start()
    except Exception as e:  # pylint: disable=W0703
        print("cronjob.py: Something went wrong.")
        print("Error message:", e)
        notify_developer(
            body=f"Scraping cronjob reported an error: {curr_date} ({get_epoch(curr_date)})"
            + f" with rror message:\n\n {e}",
            subject="Cronjob Report",
        )

    notify_developer(
        body="Today scraping cronjob has completed successfully."
        + " Check MongoDB to see today scraping data"
    )

    print(f"\nScraping cronjob finished on {round(time() - start_time, 2)} seconds")
    print("--------------------------------------------------------")


if __name__ == "__main__":
    # Blocking execution when Ctrl+C (Ctrl+Break on Windows) is pressed
    try:
        asyncio.run(cronjob())  # initiating a cronjob
    except (KeyboardInterrupt, SystemExit):
        pass
