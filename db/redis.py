"""
Reusable Redis caching utilities.
"""

import json
import redis
import hashlib
from functools import wraps
from datetime import timedelta
from urllib.parse import urlparse
from core.settings import REDIS_URI

DEFAULT_EXPIRATION = timedelta(days=14)
class RedisCache:
    def __init__(self, redis_uri: str = REDIS_URI, expiration: timedelta = DEFAULT_EXPIRATION):
        self.redis_uri = redis_uri
        self.expiration = expiration
        self.client = None

    def connect(self):
        """Connect to the Redis server."""
        url = urlparse(self.redis_uri)
        self.client = redis.Redis(
            host=url.hostname,
            port=url.port,
            username=url.username or None,
            password=url.password or None,
            decode_responses=True,
        )

    def _build_key(self, func_name, args):
        """Create a hash key from function name and arguments."""
        raw_key = f"{func_name}|{json.dumps(args, sort_keys=True, default=str)}"
        return f"cache:{func_name}:{hashlib.md5(raw_key.encode()).hexdigest()}"

    def use_cache(self, ignore_first_arg=False):
        """
        Sync decorator for caching function results in Redis.
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                if self.client is None:
                    raise RuntimeError("Redis client is not connected. Call connect() first.")

                print(f"[DEBUG] client: {self.client}")
                print(f"[DEBUG] expiration: {self.expiration}")
                print(f"[DEBUG] expiration seconds: {self.expiration.total_seconds() if self.expiration else None}")

                key_args = args[1:] if ignore_first_arg else args
                key = self._build_key(func.__name__, key_args)

                result = self.client.get(key)
                if result is not None:
                    return json.loads(result)

                value = func(*args, **kwargs)
                self.client.set(key, json.dumps(value))
                self.client.expire(key, int(self.expiration.total_seconds()))
                return value

            return wrapper
        return decorator

    def use_cache_async(self, ignore_first_arg=False):
        """
        Async decorator for caching function results in Redis.
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                if self.client is None:
                    raise RuntimeError("Redis client is not connected. Call connect() first.")

                key_args = args[1:] if ignore_first_arg else args
                key = self._build_key(func.__name__, key_args)

                result = self.client.get(key)
                if result is not None:
                    return json.loads(result)

                value = await func(*args, **kwargs)
                self.client.set(key, json.dumps(value))
                self.client.expire(key, int(self.expiration.total_seconds()))
                return value

            return wrapper
        return decorator
