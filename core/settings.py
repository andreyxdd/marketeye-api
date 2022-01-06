"""
Project Settings file
"""
import os

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

# API key to access endpoints
API_KEY = os.getenv("API_KEY")

# Developer email-notifications
DEV_SENDER_EMAIL = os.getenv("DEV_SENDER_EMAIL")
DEV_SENDER_SERVICE_PASSWORD = os.getenv("DEV_SENDER_SERVICE_PASSWORD")
DEV_SENDER_SERVICE = os.getenv("DEV_SENDER_SERVICE")
DEV_SENDER_SERVICE_PORT = os.getenv("DEV_SENDER_SERVICE_PORT")
DEV_RECIEVER_EMAIL = os.getenv("DEV_RECIEVER_EMAIL")
