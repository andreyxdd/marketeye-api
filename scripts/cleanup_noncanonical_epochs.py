"""Delete Mongo docs whose date epoch is not UTC midnight for that session date."""

import asyncio

from core.settings import MONGO_DB_NAME
from db.mongodb import close, connect, get_database
from utils.handle_datetimes import get_date_string, get_epoch


async def main() -> None:
    await connect()
    conn = await get_database()
    try:
        for coll in ("analytics", "tracking"):
            ids = []
            async for doc in conn[MONGO_DB_NAME][coll].find({}, {"date": 1}):
                epoch = doc.get("date")
                if epoch is None:
                    continue
                canonical = get_epoch(get_date_string(epoch))
                if float(epoch) != float(canonical):
                    ids.append(doc["_id"])
            if ids:
                result = await conn[MONGO_DB_NAME][coll].delete_many(
                    {"_id": {"$in": ids}}
                )
                print(f"{coll}: deleted {result.deleted_count} non-canonical docs")
            else:
                print(f"{coll}: nothing to delete")
    finally:
        await close()


if __name__ == "__main__":
    asyncio.run(main())
