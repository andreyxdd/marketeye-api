
class DataInserter():
    def __init__(self, colleciton, log_message, data):
        self.colleciton = colleciton
        self.log_message = log_message
        self.data = data

    async def run(self):
        self.filter_data()
        self.log_message(
            f"The total number of tickers to insert is {len(self.data)}")
        if self.data:
            await self.insert_data()

    async def insert_data(self):
        await self.colleciton.insert_many(self.data, ordered=False)
        self.log_message("Tickers analytics were successfully inserted")

    def filter_data(self):
        self.data = list(filter(None, self.data))
