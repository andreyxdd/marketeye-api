from pprint import pprint
from typing import Optional

from core.data import BOUNCE_CRITERIA, N_BOUNCE_PERIODS
from cronjob.frequency_analysis import FrequencyAnalysis

LONG_TERM_PERIOD_LIMIT = 4

AGGREGATE_STAGES = {
    "is-bounce": {"$match": {"bounce": {"$exists": True}}},
    "bounce-period": lambda idx: {"$match": {f"bounce.{idx}": {"$lt": 0}}},
    "project": {
        "$project": {
            "_id": False,
            "ticker": True,
            "date": True,
            "open": True,
            "close": True,
            "volume": True,
            "cp_op_precentage_diff": {"$multiply": ["$one_day_open_close_change", 100]},
            "T1": {"$arrayElemAt": ["$bounce", 0]},
            "T2": {"$arrayElemAt": ["$bounce", 1]},
            "T3": {"$arrayElemAt": ["$bounce", 2]},
            "T4": {"$arrayElemAt": ["$bounce", 3]},
            "T5": {"$arrayElemAt": ["$bounce", 4]},
            # "T6": {"$arrayElemAt": ["$bounce", 5]},
            # "T7": {"$arrayElemAt": ["$bounce", 6]},
            # "T8": {"$arrayElemAt": ["$bounce", 7]},
            # "T9": {"$arrayElemAt": ["$bounce", 8]},
            # "T10": {"$arrayElemAt": ["$bounce", 9]},
            # "T11": {"$arrayElemAt": ["$bounce", 10]},
            # "T12": {"$arrayElemAt": ["$bounce", 11]},
            # "T13": {"$arrayElemAt": ["$bounce", 12]},
            # "T14": {"$arrayElemAt": ["$bounce", 13]},
            # "T15": {"$arrayElemAt": ["$bounce", 14]},
            # "T16": {"$arrayElemAt": ["$bounce", 15]},
            # "T17": {"$arrayElemAt": ["$bounce", 16]},
            # "T18": {"$arrayElemAt": ["$bounce", 17]},
        },
    },
    "close-price-range": lambda pair: {
        "$match": {"close": {"$gte": pair[0], "$lte": pair[1]}}
    },
    "rising-stocks": {
        "$match": {"cp_op_precentage_diff": {"$gt": 0}},
    },
    "long-term-filter": {
        "$match": {
            "$expr": {
                "$and": [
                    {"$gt": ["$cp_op_precentage_diff", "$T1"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T2"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T3"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T4"]},
                    {"$gt": ["$cp_op_precentage_diff", "$T5"]},
                    # {"$gt": ["$cp_op_precentage_diff", "$T6"]},
                    # {"$gt": ["$cp_op_precentage_diff", "$T7"]},
                    # {"$gt": ["$cp_op_precentage_diff", "$T8"]},
                    # {"$gt": ["$cp_op_precentage_diff", "$T9"]},
                    # {"$gt": ["$cp_op_precentage_diff", "$T10"]},
                    # {"$gt": ["$cp_op_precentage_diff", "$T11"]},
                    # {"$gt": ["$cp_op_precentage_diff", "$T12"]},
                    # {"$gt": ["$cp_op_precentage_diff", "$T13"]},
                    # {"$gt": ["$cp_op_precentage_diff", "$T14"]},
                    # {"$gt": ["$cp_op_precentage_diff", "$T15"]},
                    # {"$gt": ["$cp_op_precentage_diff", "$T16"]},
                    # {"$gt": ["$cp_op_precentage_diff", "$T17"]},
                    # {"$gt": ["$cp_op_precentage_diff", "$T18"]},
                ]
            }
        }
    },
    "sort-risers": {
        "$sort": {"cp_op_precentage_diff": -1},
    },
    "top-20": {"$limit": 20},
    "select-fields": {
        "$project": {
            "_id": False,
            "ticker": True,
            "date": True,
            "open": True,
            "close": True,
            "volume": True,
            "cp_op_precentage_diff": True,
        }
    },
}


class BouncePostprocessor:
    top_tickers: list[str] = []

    def __init__(self, db, epoch_date, log_message, limit: Optional[int] = 20):
        self.db = db
        self.epoch_date = epoch_date
        self.log_message = log_message
        self.frequencyAnalysis = FrequencyAnalysis(
            self.db,
            self.epoch_date,
            "bounce"
        )
        self.limit = limit

    async def run(self):
        for criterion in BOUNCE_CRITERIA:
            for period_idx in range(N_BOUNCE_PERIODS):
                await self.postprocess_top_tickers(criterion, period_idx)
                self.frequencyAnalysis.set_criterion(criterion)
                self.frequencyAnalysis.set_tickers(self.top_tickers)
                await self.frequencyAnalysis.run()

    async def run_without_frequency_analysis(self):
        for criterion in BOUNCE_CRITERIA:
            for period_idx in range(N_BOUNCE_PERIODS):
                await self.postprocess_top_tickers(criterion, period_idx)

    async def retrieve_top_tickers_by(
        self, criterion: str, period_idx: int
    ) -> str:
        conditional_close_price_stage = ()
        if criterion != "unlimited":
            conditional_close_price_stage = (
                AGGREGATE_STAGES["close-price-range"](criterion),
            )

        conditional_long_term_stage = ()
        is_long_term = period_idx > LONG_TERM_PERIOD_LIMIT
        if is_long_term:
            conditional_long_term_stage = (
                AGGREGATE_STAGES["long-term-filter"],
            )

        pipeline = [
            {"$match": {"date": self.epoch_date}},
            *conditional_close_price_stage,
            AGGREGATE_STAGES["bounce-period"](period_idx),
            AGGREGATE_STAGES["project"],
            AGGREGATE_STAGES["rising-stocks"],
            *conditional_long_term_stage,
            AGGREGATE_STAGES["sort-risers"],
            AGGREGATE_STAGES["top-20"],
            {"$project": {"_id": False, "ticker": True}},
        ]
        cursor = self.db.timeseries.aggregate(pipeline)
        query_result = await cursor.to_list(length=self.limit)

        self.top_tickers = [item["ticker"] for item in query_result]

    async def update_criterion_collection(self, criterion: str, period_idx: int):
        await self.db[str(criterion)].update_one(
            {"date": self.epoch_date},
            {
                "$set": {
                    "date": self.epoch_date,
                    f"tickers.{period_idx}": ",".join(self.top_tickers)
                },
            },
            upsert=True
        )

    async def postprocess_top_tickers(self, criterion: str, period_idx: int):
        # TODO: Remove limit argument
        await self.retrieve_top_tickers_by(criterion, period_idx)
        await self.update_criterion_collection(criterion, period_idx)
