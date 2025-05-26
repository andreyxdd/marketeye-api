"""
Methods to handle connection to Redis
"""
from datetime import timedelta
from functools import wraps
import json
from urllib.parse import urlparse
import redis

from core.settings import REDIS_URI

EXPIRATION_TIME = timedelta(days=14)
class Database:  # pylint: disable=R0903
    """
    Class represeting Redis databse
    """

    client: redis.Redis = None

db = Database()

async def get_database() -> redis.Redis:
    """
    Returns:
        AsyncIOMotorClient: return Redis database object
    """
    return db.client

async def connect():
    """Connect to Redis"""
    print("Connecting to Redis...")
    url = urlparse(REDIS_URI)
    db.client = redis.Redis(
        host=url.hostname,
        port=url.port,
        decode_responses=True,
        username="default",
        password=url.password,
    )

    if db.client is None:
        raise Exception("Failed to connect to Redis")

    print(f"Connected to Redis: {type(db.client)}")

async def flushdb():
    """Flush all data in the Redis"""
    db.client.flushdb()

def use_cache(ignore_first_arg=False):
    """
    Decorator that caches the results of the function call.
    """

    print(f'here 1 {type(db.client)}')
    def decorator(func):
        print(f'here 2 {type(db.client)}')
        @wraps(func)
        def wrapper(*args, **kwargs):
            print('here 3')
            # Generate the cache key from the function's arguments.
            key_parts = [func.__name__] + list(args)
            if ignore_first_arg:
                key_parts.pop(1)

            print('here 4')
            key = "-".join([str(k) for k in key_parts])
            print(f'here 5 {type(db.client)}')
            print(f'key {key}')
            result = db.client.get(key)
            print('here 6')

            if result is None:
                print('here 7')
                # Run the function and cache the result for next time.
                value = func(*args, **kwargs)
                value_json = json.dumps(value)
                db.client.set(key, value_json)
                db.client.expire(key, EXPIRATION_TIME)
            else:
                print('here 8')
                # If redisClient is already returning a string (decode_responses=True), skip decode
                value_json = result
                if isinstance(result, bytes):
                    value_json = result.decode("utf-8")
                value = json.loads(value_json)

            print('here 9')
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
            result = db.client.get(key)

            if result is None:
                # Run the function and cache the result for next time.
                value = await func(*args, **kwargs)
                value_json = json.dumps(value)
                db.client.set(key, value_json)
                db.client.expire(key, EXPIRATION_TIME)
            else:
                # Skip the function entirely and use the cached value instead.
                value_json = result.decode("utf-8")
                value = json.loads(value_json)

            return value

        return wrapper

    return decorator
