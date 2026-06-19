"""MongoDB storage monitor and prune executor."""

import argparse
import asyncio
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.settings import (
    MONGO_STORAGE_LIMIT_BYTES,
    MONGO_STORAGE_PRUNE_TARGET_RATIO,
    MONGO_STORAGE_PRUNE_TRIGGER_RATIO,
)
from db.crud.mongo_storage import (
    get_mongo_storage_ratio,
    prune_oldest_published_mongo_session,
)
from db.mongodb import close as close_mongo
from db.mongodb import connect as connect_mongo
from db.mongodb import get_database as get_mongo_database
from db.postgres import close as close_postgres
from db.postgres import connect as connect_postgres
from db.postgres import get_pool as get_postgres_pool
from utils.handle_telegram import notify_developer


async def run_monitor(check_only: bool = False, manage_connections: bool = True) -> dict:
    """Check Mongo storage ratio and prune oldest published sessions when threshold is crossed.

    When ``manage_connections`` is False (embedded cron path), the caller owns Postgres
    lifecycle; this function skips connect/close for both Postgres and Mongo.
    """
    if manage_connections:
        await connect_postgres()
    await connect_mongo()
    pool = await get_postgres_pool()
    conn = await get_mongo_database()
    try:
        size_bytes, ratio = await get_mongo_storage_ratio(conn, MONGO_STORAGE_LIMIT_BYTES)
        result = {
            "check_only": check_only,
            "size_bytes": size_bytes,
            "ratio": ratio,
            "pruned_dates": [],
        }

        if ratio < MONGO_STORAGE_PRUNE_TRIGGER_RATIO:
            print(f"mongo_storage_monitor: ratio={ratio:.4f}; below threshold")
            return result

        notify_developer(
            subject="Mongo Storage Alert",
            body=(
                "Mongo storage reached prune threshold.\n"
                f"size_bytes={size_bytes}\n"
                f"ratio={ratio:.4f}\n"
                f"limit_bytes={MONGO_STORAGE_LIMIT_BYTES}"
            ),
        )
        print(f"mongo_storage_monitor: ratio={ratio:.4f}; alert sent")

        if check_only:
            return result

        while ratio > MONGO_STORAGE_PRUNE_TARGET_RATIO:
            pruned_date = await prune_oldest_published_mongo_session(pool, conn)
            if pruned_date is None:
                break
            result["pruned_dates"].append(pruned_date)
            size_bytes, ratio = await get_mongo_storage_ratio(conn, MONGO_STORAGE_LIMIT_BYTES)
            result["size_bytes"] = size_bytes
            result["ratio"] = ratio
            print(
                "mongo_storage_monitor: pruned"
                f" session_date={pruned_date}; ratio={ratio:.4f}"
            )

        return result
    finally:
        if manage_connections:
            await close_mongo()
            await close_postgres()


def _parse_args():
    parser = argparse.ArgumentParser(description="Check and prune Mongo storage")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Check usage and alert, but do not prune",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    summary = asyncio.run(run_monitor(check_only=args.check_only))
    print(f"mongo_storage_monitor: done {summary}")
