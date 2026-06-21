"""Remove published_dates rows with no archived tickers."""

import asyncio

from db.postgres import close, connect, get_pool


async def main() -> None:
    await connect()
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            artifacts = await conn.execute(
                """
                DELETE FROM published_artifacts a
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM published_tickers t
                    WHERE t.session_date = a.session_date
                      AND t.market = a.market
                )
                """
            )
            dates = await conn.execute(
                """
                DELETE FROM published_dates d
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM published_tickers t
                    WHERE t.session_date = d.session_date
                      AND t.market = d.market
                )
                """
            )
        print(f"ghost cleanup: {dates}; orphan artifacts: {artifacts}")
    finally:
        await close()


if __name__ == "__main__":
    asyncio.run(main())
