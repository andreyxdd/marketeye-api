"""
Methods to handle connection to Redis
"""
from datetime import timedelta
from functools import wraps
import json
from urllib.parse import urlparse

import redis

from core.settings import REDIS_URI

url = urlparse(REDIS_URI)
redisClient = redis.Redis(
    host=url.hostname,
    port=url.port,
    password=url.password,
    ssl=(url.scheme == "rediss"),
    ssl_cert_reqs='required'
)
print(f"REDIS VERSION {redis.__version__}")
print(f"REDIS URI {REDIS_URI}")
# redisClient.flushdb()
EXPIRATION_TIME = timedelta(days=14)


def use_cache(ignore_first_arg=False):
    """
    Decorator that caches the results of the function call.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate the cache key from the function's arguments.
            key_parts = [func.__name__] + list(args)
            if ignore_first_arg:
                key_parts.pop(1)

            key = "-".join([str(k) for k in key_parts])
            result = redisClient.get(key)

            if result is None:
                # Run the function and cache the result for next time.
                value = func(*args, **kwargs)
                value_json = json.dumps(value)
                redisClient.set(key, value_json)
                redisClient.expire(key, EXPIRATION_TIME)
            else:
                # Skip the function entirely and use the cached value instead.
                value_json = result.decode("utf-8")
                value = json.loads(value_json)

            return value

        return wrapper

    return decorator


def use_cache_async(ignore_first_arg=False):
    """
    Asynchronus decorator that caches the results of the function call.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate the cache key from the function's arguments.
            key_parts = [func.__name__] + list(args)
            if ignore_first_arg:
                key_parts.pop(1)

            key = "-".join([str(k) for k in key_parts])
            result = redisClient.get(key)

            if result is None:
                # Run the function and cache the result for next time.
                value = await func(*args, **kwargs)
                value_json = json.dumps(value)
                redisClient.set(key, value_json)
                redisClient.expire(key, EXPIRATION_TIME)
            else:
                # Skip the function entirely and use the cached value instead.
                value_json = result.decode("utf-8")
                value = json.loads(value_json)

            return value

        return wrapper

    return decorator
