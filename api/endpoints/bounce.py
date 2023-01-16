"""
Endpoints to access data processed with bounce algorithm
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from db.crud.bounce import get_bounce_dates, get_bounce_stocks
from db.mongodb import AsyncIOMotorClient, get_database
from utils.handle_validation import validate_api_key, validate_date_string

bounce_router = APIRouter()


@bounce_router.get("/", tags=["Bounce"])
async def bounce():
    """
    Initial bounce route endpoint
    """
    return Response("Hello World! It's an Bounce Router")


@bounce_router.get("/get_bounce_stocks", tags=["Bounce"])
async def read_bounce_stocks(
    period: int = Query(
        default=None,
        description="""Number of past periods to include in the bounce analysis.
        This number should lie within the range from 1 to 18.""",
    ),
    date: str = Depends(validate_date_string),
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    db: AsyncIOMotorClient = Depends(get_database),
) -> dict:
    """
    Endpoint to get analytics (both base and extra) for a single stock

    Returns: see output for the _get_bounce_stocks_ function
    """

    if period not in range(1, 19):
        raise HTTPException(status_code=422, detail="No such period implemented.")

    return await get_bounce_stocks(db, date, period)


@bounce_router.get("/get_dates", tags=["Bounce"])
async def read_dates(
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    db: AsyncIOMotorClient = Depends(get_database),
) -> dict:
    """
    Endpoint to get dates for which bounce algorithm data exists in the database

    Returns: List of epoch dates ("dates")
    """

    return await get_bounce_dates(db)
