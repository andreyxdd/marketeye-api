"""
Routes to test API
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from utils.handle_datetimes import is_valid_date
from utils.handle_validation import validate_api_key

tests_router = APIRouter()


@tests_router.get("/", tags=["Tests"])
async def test():
    """
    Initial tests route endpoint
    """
    return Response("Hello World! It's a Tests Router")


@tests_router.get("/validate_date_string", tags=["Tests"])
async def run_date_string_validation(
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
    date_string: Optional[str] = Query(
        default="2021-12-12",
        description="Date string to validate the format",
    ),
):
    """
    Endpoint to validate date string

    Returns: {"isValidDate": bollean, "isValidApiKey": bollean}
    """

    return {"isValidDate": is_valid_date(date_string), "isValidApiKey": True}
