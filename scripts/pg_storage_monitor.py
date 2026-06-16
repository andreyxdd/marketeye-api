"""PostgreSQL storage monitor and prune executor."""

import argparse
import asyncio
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.settings import PG_STORAGE_LIMIT_BYTES
from db.crud.published_archive import get_storage_ratio, prune_oldest_session_date
from db.postgres import close as close_postgres
from db.postgres import connect as connect_postgres
from db.postgres import get_pool as get_postgres_pool
from utils.handle_emails import notify_developer


PRUNE_TRIGGER_RATIO = 0.85
PRUNE_TARGET_RATIO = 0.70


async def run_monitor(check_only: bool = False) -> dict:
    """Check storage ratio and prune oldest published dates when threshold is crossed."""
    await connect_postgres()
    pool = await get_postgres_pool()
    try:
        size_bytes, ratio = await get_storage_ratio(pool, PG_STORAGE_LIMIT_BYTES)
        result = {
            "check_only": check_only,
            "size_bytes": size_bytes,
            "ratio": ratio,
            "pruned_dates": [],
        }

        if ratio < PRUNE_TRIGGER_RATIO:
            print(f"pg_storage_monitor: ratio={ratio:.4f}; below threshold")
            return result

        notify_developer(
            subject="Postgres Storage Alert",
            body=(
                "Postgres storage reached prune threshold.\n"
                f"size_bytes={size_bytes}\n"
                f"ratio={ratio:.4f}\n"
                f"limit_bytes={PG_STORAGE_LIMIT_BYTES}"
            ),
        )
        print(f"pg_storage_monitor: ratio={ratio:.4f}; alert sent")

        if check_only:
            return result

        while ratio > PRUNE_TARGET_RATIO:
            pruned_date = await prune_oldest_session_date(pool)
            if pruned_date is None:
                break
            result["pruned_dates"].append(pruned_date)
            size_bytes, ratio = await get_storage_ratio(pool, PG_STORAGE_LIMIT_BYTES)
            result["size_bytes"] = size_bytes
            result["ratio"] = ratio
            print(
                "pg_storage_monitor: pruned"
                f" session_date={pruned_date}; ratio={ratio:.4f}"
            )

        return result
    finally:
        await close_postgres()


def _parse_args():
    parser = argparse.ArgumentParser(description="Check and prune Postgres storage")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Check usage and alert, but do not prune",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    summary = asyncio.run(run_monitor(check_only=args.check_only))
    print(f"pg_storage_monitor: done {summary}")
