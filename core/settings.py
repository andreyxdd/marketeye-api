"""
Project Settings file
"""
import os
from dotenv import load_dotenv

load_dotenv()

DEFAULT_ROUTE_STR = "/api"

# Mongo configuration
MONGO_MAX_CONNECTIONS = int(os.getenv("MAX_CONNECTIONS_COUNT", "10"))
MONGO_MIN_CONNECTIONS = int(os.getenv("MIN_CONNECTIONS_COUNT", "10"))
MONGO_USERNAME = os.getenv("MONGO_USERNAME")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    MONGO_URI = (
        "mongodb+srv://"
        + f"{MONGO_USERNAME}:{MONGO_PASSWORD}@cluster0.xlodq.mongodb.net/"
        + f"{MONGO_DB_NAME}?retryWrites=true&w=majority"
    )

# Redis configurations
REDIS_URI = os.getenv("REDIS_URI") or os.getenv("REDISCLOUD_URL")

# PostgreSQL read-model configuration
DATABASE_URL = os.getenv("DATABASE_URL")
PG_STORAGE_LIMIT_BYTES = int(os.getenv("PG_STORAGE_LIMIT_BYTES", "10737418240"))
MONGO_HOT_WINDOW_DAYS = int(os.getenv("MONGO_HOT_WINDOW_DAYS", "70"))
OHLCV_CACHE_DISABLED = os.getenv("OHLCV_CACHE_DISABLED", "0") == "1"
OHLCV_LOOKBACK_BUFFER_DAYS = int(
    os.getenv("OHLCV_LOOKBACK_BUFFER_DAYS", str(MONGO_HOT_WINDOW_DAYS + 85))
)
MONGO_STORAGE_LIMIT_BYTES = int(os.getenv("MONGO_STORAGE_LIMIT_BYTES", "536870912"))
MONGO_STORAGE_PRUNE_TRIGGER_RATIO = float(
    os.getenv("MONGO_STORAGE_PRUNE_TRIGGER_RATIO", "0.85")
)
MONGO_STORAGE_PRUNE_TARGET_RATIO = float(
    os.getenv("MONGO_STORAGE_PRUNE_TARGET_RATIO", "0.70")
)

# API key to access endpoints
API_KEY = os.getenv("API_KEY")

# Developer Telegram notifications
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

# Quandl API key
QUANDL_API_KEY = os.getenv("QUANDL_API_KEY")
QUANDL_RATE_LIMIT = int(os.getenv("QUANDL_RATE_LIMIT", 4900))
QUANDL_SLEEP_MINUTES = int(os.getenv("QUANDL_SLEEP_MINUTES", 10))

# Polygon API key
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

# EODHD API key (Toronto / TO market)
EODHD_API_KEY = os.getenv("EODHD_API_KEY")

# Cron parallel ingest
CRON_MAX_WORKERS = int(os.getenv("CRON_MAX_WORKERS", "15"))
CRON_INSERT_BATCH_SIZE = int(os.getenv("CRON_INSERT_BATCH_SIZE", "500"))

# Session probe tickers (LastCompletedSession resolution)
PROBE_TICKER_US = os.getenv("PROBE_TICKER_US", "SPY")
PROBE_TICKER_TO = os.getenv("PROBE_TICKER_TO", "SHOP")

# URL setting to get market analytics using external datasets
MI_BASE_URL = os.getenv("MI_BASE_URL")
MI_SP500_CODE = os.getenv("MI_SP500_CODE", "998434")
MI_SP500_DATASET = os.getenv("MI_SP500_DATASET", "SNC")
MI_VIX_CODE = os.getenv("MI_VIX_CODE", "1689105")
MI_VIX_DATASET = os.getenv("MI_VIX_DATASET", "MDE")
YAHOO_BASE_FCF_URL = os.getenv("YAHOO_BASE_FCF_URL")

# Default headers objects to make requests to external APIs
DEFAULT_HEADERS = {
    "user-agent": os.getenv("USER_AGENT"),
    "sec-fetch-mode": "cors",
    "accept-language": "en-GB,en;q=0.9,en-US;q=0.8,ru;q=0.7",
    "accept-encoding": "gzip, deflate, br",
}

# Date for scraping pipelines
DATE_TO_SCRAPE = os.getenv("DATE_TO_SCRAPE")
