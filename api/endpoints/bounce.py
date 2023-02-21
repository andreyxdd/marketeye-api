"""
Endpoints to access data processed with bounce algorithm
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from db.crud.bounce import get_bounce_dates, get_bounce_stocks, get_tracked_stocks
from db.mongodb import AsyncIOMotorClient, get_database
from utils.handle_validation import (
    validate_api_key,
    validate_bounce_period,
    validate_date_string,
)

bounce_router = APIRouter()


@bounce_router.get("/", tags=["Bounce"])
async def bounce():
    """
    Initial bounce route endpoint
    """
    return Response("Hello World! It's an Bounce Router")


@bounce_router.get("/get_bounce_stocks", tags=["Bounce"])
async def read_bounce_stocks(
    period: int = Depends(validate_bounce_period),
    date: str = Depends(validate_date_string),
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    db: AsyncIOMotorClient = Depends(get_database),
) -> dict:
    """
    Endpoint to get top-20 stocks selected by the bounce analysis for the given date.
    For each ticker, volume, closing/opening prices and their precntage differences are
    in the return.

    Returns: see output for the _get_bounce_stocks_ function
    """

    return await get_bounce_stocks(db, date, period)


@bounce_router.get("/get_tracked_stocks", tags=["Bounce"])
async def read_tracked_stocks(
    date: str = Depends(validate_date_string),
    tickers: str = Query(
        default=None,
        description="""Tickers of the stocks to track.
        Pass list as a string separating tickers by a comma without any spaces.""",
    ),
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    db: AsyncIOMotorClient = Depends(get_database),
) -> dict:
    """
    Endpoint to get close/opening prices, thier difference in precentages, and volume
    of the stocks in the provided list and on the given trading day.

    Returns: see output for the _get_bounce_stocks_ function
    """

    return await get_tracked_stocks(db, date, tickers.split(","))


@bounce_router.get("/get_frequencies", tags=["Bounce"])
async def read_frequencies(
    period: int = Depends(validate_bounce_period),
    date: str = Depends(validate_date_string),
    tickers: str = Query(
        default=None,
        description="""Stock tickers to count their frequency.
        Pass list as a string separating tickers by a comma without any spaces.""",
    ),
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    db: AsyncIOMotorClient = Depends(get_database),
) -> dict:
    """
    Endpoint to count how often each ticker in the provided array has appeard in
    the top 20 during the given period

    Returns: List of strings representing the period when the ticker occoured in
    the top 20, e.g., "T-2, T-4, T-6"
    """
    tickers = tickers.split(",")
    frequencies = [""] * len(tickers)
    for idx, ticker in enumerate(tickers):
        curr_period = period
        while curr_period > 1:
            # searching from the highest period to the lowest
            curr_period = curr_period - 1

            # function is cached so it's alright to iterate
            arr = await get_bounce_stocks(db, date, curr_period)
            for item in arr:
                if ticker == item["ticker"]:
                    frequencies[idx] = frequencies[idx] + f"T-{curr_period}, "
                    # ticker can appear only once, no need to continue looping
                    break

        # if there is ticker frequency
        if frequencies[idx]:
            # removing last two chars from the string
            frequencies[idx] = frequencies[idx][:-2]

    return frequencies


@bounce_router.get("/get_dates", tags=["Bounce"])
async def read_dates(
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    db: AsyncIOMotorClient = Depends(get_database),
) -> dict:
    """
    Endpoint to get dates for which bounce algorithm data exists in the database

    Returns: List of epoch dates ("dates") sorted in ascending order
    """
    return await get_bounce_dates(db)
