from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from time import sleep

from core.settings import QUANDL_RATE_LIMIT, QUANDL_SLEEP_MINUTES
from utils.quandl import get_quandl_tickers, get_single_ticker_analytics

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class DataAssembler():
    tickers: list[str] = []
    n_tickers_initially: int = 0
    ticekrs_partitions: list[list[str]] = []
    data = []

    def __init__(self, collection, date, epoch_date, log_message, data):
        self.collection = collection
        self.date = date
        self.epoch_date = epoch_date
        self.log_message = log_message
        self.data = data

    async def run(self):
        await self.retrieve_tickers()
        self.make_tickers_partitions()
        self.analyze_partitions()

    async def retrieve_tickers(self):
        # TODO: remove limit below
        quandl_tickers = get_quandl_tickers(self.date)[5000:5200]

        cursor = await self.collection.distinct("ticker", {"date": self.epoch_date})
        db_tickers = list(cursor)
        self.tickers = list(set(quandl_tickers) - set(db_tickers))
        self.n_tickers_initially = len(self.tickers)

    def make_tickers_partitions(self):
        if self.n_tickers_initially >= QUANDL_RATE_LIMIT:
            while len(self.tickers) >= QUANDL_RATE_LIMIT:
                partition: list(str) = self.tickers[:QUANDL_RATE_LIMIT]
                # this mutates tickers:
                self.tickers = self.tickers[QUANDL_RATE_LIMIT:]
                self.ticekrs_partitions.append(partition)
            # adding left-overs:
            self.ticekrs_partitions.append(self.tickers)
        else:
            self.ticekrs_partitions.append(self.tickers)

    def delay_partition_analysis(self):
        log.info(
            "\n--------------------------------------------------------------------"
            +
            " Sleeping for 10 minutes to prevent exceeding Quandl API rate limit\n"
            +
            "--------------------------------------------------------------------\n"
        )
        sleep(QUANDL_SLEEP_MINUTES * 60 + 0.5)

    def analyze_single_partition(self, partition):
        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(get_single_ticker_analytics, ticker, self.date)
                for ticker in partition
            ]

            for future in as_completed(futures):
                self.data.append(future.result())

    def analyze_partitions(self):
        if self.n_tickers_initially == 0:
            self.log_message(f"No tickers to insert for {self.date}")
            return

        self.log_message(
            f"The total number of tickers to analyze is {self.n_tickers_initially}"
        )

        for partition in self.ticekrs_partitions:
            self.analyze_single_partition(partition)
