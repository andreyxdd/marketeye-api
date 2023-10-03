from typing import Optional

from core.data import ANALYTICS_CRITERIA
from cronjob.frequency_analysis import FrequencyAnalysis

ANALYTICS_CRITERIA = ["macd"]


class AnalyticsPostprocessor:
    top_tickers: list[str] = []

    def __init__(self, db, epoch_date, log_message, limit: Optional[int] = 20):
        self.db = db
        self.epoch_date = epoch_date
        self.log_message = log_message
        self.frequencyAnalysis = FrequencyAnalysis(
            self.db,
            self.epoch_date,
            "analytics"
        )
        self.limit = limit

    async def run(self):
        for criterion in ANALYTICS_CRITERIA:
            await self.postprocess_top_tickers(criterion)
            self.frequencyAnalysis.set_criterion(criterion)
            self.frequencyAnalysis.set_tickers(self.top_tickers)
            await self.frequencyAnalysis.run()

    async def run_without_frequency_analysis(self):
        for criterion in ANALYTICS_CRITERIA:
            await self.postprocess_top_tickers(criterion)

    async def retrieve_top_tickers_by(
        self, criterion: str
    ) -> str:
        cursor = (
            self.db.timeseries
            .find(
                {"date": self.epoch_date},
                {"_id": False, "ticker": True},
            )
            .sort(criterion, -1)
            .limit(self.limit)
        )
        items = await cursor.to_list(length=self.limit)

        self.top_tickers = [item["ticker"] for item in items]

    async def update_criterion_collection(self, criterion: str):
        await self.db[criterion].find_one_and_replace(
            {"date": self.epoch_date},
            {"date": self.epoch_date, "tickers": ",".join(self.top_tickers)},
            upsert=True
        )

    async def postprocess_top_tickers(self, criterion: str):
        # TODO: Remove limit argument
        await self.retrieve_top_tickers_by(criterion)
        if self.top_tickers:
            await self.update_criterion_collection(criterion)
