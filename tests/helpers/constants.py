"""Shared constants for the local test suite."""

FIXTURE_DATE = "2024-06-03"
FIXTURE_API_KEY = "test-api-key-e2e"
HISTORY_WEEKDAYS = 50
LIST_LIMIT = 20

FIXTURE_TICKERS = [
    "AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA", "TSLA", "JPM", "V", "UNH",
    "XOM", "JNJ", "WMT", "PG", "MA", "HD", "CVX", "LLY", "AVGO", "COST",
    "ORCL", "AMD", "PEP", "KO", "DIS", "BAC", "CRM", "NFLX", "ABBV", "MRK",
    "TMO", "CSCO", "ACN", "LIN", "MCD", "ADBE", "WFC", "DHR", "PM", "TXN",
    "INTU", "QCOM", "UNP", "AMGN", "HON", "LOW", "UPS", "IBM", "GE", "CAT",
]

CALC_TICKERS = ["AAPL", "MSFT", "GOOG"]
PIPELINE_TICKERS = ["AAPL", "MSFT", "GOOG"]

CRITERIA = [
    "one_day_avg_mf",
    "three_day_avg_mf",
    "volume",
    "three_day_avg_volume",
    "macd",
]

BY_CRITERIA_KEYS = [
    "by_one_day_avg_mf",
    "by_three_day_avg_mf",
    "by_volume",
    "by_three_day_avg_volume",
    "by_macd",
]

DATA_PROPS_KEYS = [
    "ticker",
    "date",
    "macd",
    "one_day_avg_mf",
    "three_day_avg_mf",
    "volume",
    "three_day_avg_volume",
    "mfi",
    "fcf",
    "frequencies",
    "mentions_over_one_day",
    "mentions_over_two_days",
    "mentions_over_three_days",
]

MARKET_KEYS = [
    "SP500",
    "VIX",
    "VIX1",
    "VIX2",
    "VIX_50days_EMA",
    "normalazied_CVI_slope",
]
