"""
Endpoints to access stock market analytics
"""

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from db.crud.analytics import (
    get_analytics_sorted_by,
    get_dates,
)
from db.mongodb import AsyncIOMotorClient, get_database
from utils.handle_validation import validate_api_key, validate_date_string

bounce_router = APIRouter()


@bounce_router.get("/", tags=["Bounce"])
async def bounce():
    """
    Initial bounce route endpoint
    """
    return Response("Hello World! It's an Bounce Router")


@bounce_router.get("/get_analytics_lists_by_criterion", tags=["Bounce"])
async def read_analytics_lists_by_criterion(
    date: str = Depends(validate_date_string),
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    db: AsyncIOMotorClient = Depends(get_database),
) -> dict:
    """
    Endpoint to get analytics (both base and extra) for a single stock

    Returns: See output for the functions _compute_base_analytics_ and _compute_extra_analytics_
    """

    return {"one_day_avg_mf": await get_analytics_sorted_by(db, date, "one_day_avg_mf")}


@bounce_router.get("/get_dates", tags=["Bounce"])
async def read_dates(
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    db: AsyncIOMotorClient = Depends(get_database),
) -> dict:
    """
    Endpoint to get dates for which bounce algorithm data exists in the database

    Returns: List of epoch dates ("dates")
    """

    return await get_dates(db)
