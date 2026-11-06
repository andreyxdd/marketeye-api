"""Dry-run, apply, or resume canonical StockBounce historical backfill."""

import argparse
import asyncio
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.postgres import close as close_postgres
from db.postgres import connect as connect_postgres
from db.postgres import get_pool
from services.stock_bounce.adapters import (
    EodhdStockBounceAdapter,
    PostgresBackfillStoreV2,
    PostgresLocalBarsAdapter,
)
from services.stock_bounce.backfill import (
    StockBounceBackfillV2,
    StockBounceStorageLimitError,
)


async def run(args) -> dict:
    await connect_postgres()
    try:
        pool = await get_pool()
        runner = StockBounceBackfillV2(
            PostgresBackfillStoreV2(pool),
            PostgresLocalBarsAdapter(pool),
            EodhdStockBounceAdapter(),
        )
        return await runner.run(
            resume_run_id=args.resume_run_id,
            dry_run=args.dry_run,
            force=args.force,
        )
    finally:
        await close_postgres()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume-run-id")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main():
    try:
        report = asyncio.run(run(parse_args()))
    except StockBounceStorageLimitError as error:
        print(
            json.dumps(
                {
                    "error": {
                        "code": "STORAGE_LIMIT_EXCEEDED",
                        "message": str(error),
                    }
                }
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from error
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("unpublished"):
        for date_string in report["unpublished"]:
            print(
                f"stock_bounce_backfill: {date_string}: "
                f"{report['errors'].get(date_string, 'unpublished')}",
                file=sys.stderr,
            )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
