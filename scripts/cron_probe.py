"""Report whether the scheduled analytics cron has unpublished sessions."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.markets import list_markets
from db.postgres import close as close_postgres
from db.postgres import connect as connect_postgres
from db.postgres import get_pool as get_postgres_pool
from services.cron_dates import needs_ingest


async def probe_needs_work(pool) -> bool:
    """Return true when any configured market needs ingest."""
    for market in list_markets():
        if await needs_ingest(pool, market):
            return True
    return False


def write_needs_work(needs_work: bool) -> None:
    """Print and optionally export GHA's step output."""
    value = str(needs_work).lower()
    print(f"needs_work={value}")
    output_path = os.getenv("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output_file:
            output_file.write(f"needs_work={value}\n")


async def main() -> None:
    await connect_postgres()
    try:
        write_needs_work(await probe_needs_work(await get_postgres_pool()))
    finally:
        await close_postgres()


if __name__ == "__main__":
    asyncio.run(main())
