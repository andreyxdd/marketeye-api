from core.data import N_FREQUENCY_PERIODS


class FrequencyAnalysis:
    criterion = ""
    tickers = []
    tickers_in_previous_periods = []
    frequency_string = ""

    def __init__(self, db, epoch_date: int, postprocessing_type: str):
        self.db = db
        self.epoch_date = epoch_date
        self.postprocessing_type = postprocessing_type

    def set_criterion(self, criterion: str):
        self.criterion = criterion

    def set_tickers(self, tickers):
        self.tickers = tickers

    async def run(self):
        await self.retrieve_tickers_in_previous_periods()
        await self.count_and_upsert_frequencies()

    async def retrieve_tickers_in_previous_periods(self):
        cursor = (
            self.db[self.criterion]
            .find(
                {"date": {"$lt": self.epoch_date}},
                {"_id": False, "tickers": True}
            )
            .sort("date", -1)
            .limit(N_FREQUENCY_PERIODS)
        )

        self.tickers_in_previous_periods = [
            item["tickers"].split(",") for item in await cursor.to_list(length=N_FREQUENCY_PERIODS)
        ]

    def make_frequency_string_for(self, ticker):
        frequency_string = ""
        for idx, previous_tickers in enumerate(self.tickers_in_previous_periods):
            if ticker in previous_tickers:
                frequency_string += f"T-{idx+1}, "

        self.frequency_string = frequency_string[:-2]

    async def count_and_upsert_frequencies(self):
        for ticker in self.tickers:
            self.make_frequency_string_for(ticker)

            await self.db.timeseries.update_one(
                {"date": self.epoch_date, "ticker": ticker},
                {
                    "$set": {
                        f"frequencies.{self.postprocessing_type}.{self.criterion}": self.frequency_string,
                    }
                },
                upsert=True,
            )
