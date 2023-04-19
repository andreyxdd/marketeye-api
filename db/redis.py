"""
Methods to handle connection to Redis
"""
from urllib.parse import urlparse

import redis

from core.settings import REDIS_URI

url = urlparse(REDIS_URI)
cacheStore = redis.Redis(
    host=url.hostname,
    port=url.port,
    password=url.password,
    ssl=True,
    ssl_cert_reqs=None,
)
