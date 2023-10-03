
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from typing import Optional
from core.data import ANALYTICS_CRITERIA
from cronjob.analytics_postprocessor import AnalyticsPostprocessor
from cronjob.bounce_postprocessor import BouncePostprocessor
from cronjob.data_assembler import DataAssembler
from cronjob.data_inserter import DataInserter

from utils.handle_datetimes import get_epoch

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class Cronjob:
    notification_messages: list[str] = []
    data = []

    def __init__(self, db, date):
        self.db = db
        self.date = date
        self.epoch_date = get_epoch(date)
        self.dataAssembler = DataAssembler(
            self.db.timeseries,
            self.date,
            self.epoch_date,
            self.log_message,
            self.data
        )
        self.dataInserter = DataInserter(
            self.db.timeseries,
            self.log_message,
            self.data
        )
        self.analalyticsPostprocessor = AnalyticsPostprocessor(
            self.db,
            self.epoch_date,
            self.log_message,
        )
        self.bouncePostprocessor = BouncePostprocessor(
            self.db,
            self.epoch_date,
            self.log_message,
        )

    def log_message(self, msg):
        log.info(msg)
        self.notification_messages.append(msg)

    async def run(self):
        await self.dataAssembler.run()
        await self.dataInserter.run()
        await self.analalyticsPostprocessor.run_without_frequency_analysis()
        await self.bouncePostprocessor.run_without_frequency_analysis()
