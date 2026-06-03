#!/usr/bin/env python3
"""Backfill market='US' on legacy analytics and tracking documents."""

import argparse
import asyncio

from core.settings import MONGO_DB_NAME
from db.mongodb import connect as connect_mongo, close as close_mongo, db


async def backfill(dry_run: bool = False) -> None:
    await connect_mongo()
    client = db.client

    for collection in ("analytics", "tracking"):
        query = {"market": {"$exists": False}}
        count = await client[MONGO_DB_NAME][collection].count_documents(query)
        print(f"{collection}: {count} documents missing market field")
        if not dry_run and count:
            result = await client[MONGO_DB_NAME][collection].update_many(
                query, {"$set": {"market": "US"}}
            )
            print(f"{collection}: modified {result.modified_count}")

    await close_mongo()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(backfill(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
