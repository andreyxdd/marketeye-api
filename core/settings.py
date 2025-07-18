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
MONGO_URI = (
    "mongodb+srv://"
    + f"{MONGO_USERNAME}:{MONGO_PASSWORD}@cluster0.xlodq.mongodb.net/"
    + f"{MONGO_DB_NAME}?retryWrites=true&w=majority"
)

# Redis configurations
REDIS_URI = os.getenv("REDISCLOUD_URL")

# API key to access endpoints
API_KEY = os.getenv("API_KEY")

# Developer email-notifications
DEV_SENDER_EMAIL = os.getenv("DEV_SENDER_EMAIL")
DEV_SENDER_SERVICE_PASSWORD = os.getenv("DEV_SENDER_SERVICE_PASSWORD")
DEV_SENDER_SERVICE = os.getenv("DEV_SENDER_SERVICE")
DEV_SENDER_SERVICE_PORT = os.getenv("DEV_SENDER_SERVICE_PORT")
DEV_RECIEVER_EMAIL = os.getenv("DEV_RECIEVER_EMAIL")
ADDITIONAL_DEV_RECIEVER_EMAIL = os.getenv("ADDITIONAL_DEV_RECIEVER_EMAIL")

# Quandl API key
QUANDL_API_KEY = os.getenv("QUANDL_API_KEY")
QUANDL_RATE_LIMIT = int(os.getenv("QUANDL_RATE_LIMIT", 4900))
QUANDL_SLEEP_MINUTES = int(os.getenv("QUANDL_SLEEP_MINUTES", 10))

# Polygon API key
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

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
