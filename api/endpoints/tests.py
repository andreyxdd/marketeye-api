"""
Routes to test API
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from core.settings import API_KEY
from utils.handle_datetimes import is_valid_date
from db.mongodb import AsyncIOMotorClient, get_database

tests_router = APIRouter()


@tests_router.get("/")
async def home():
    """
    Initial tests route

    Returns:

        Response: welcome sign
    """
    return Response("Hello World! It's a Tests Router")


@tests_router.get("/validate_date_string")
async def run_date_string_validation(
    api_key: str,
    db: AsyncIOMotorClient = Depends(get_database),
    date_string: Optional[str] = "2021-12-12",
):
    """
    Endpoint to validate date string

    Args:

        api_key (str): key to allow/disallow a request

        db (AsyncIOMotorClient, optional): database object. Defaults to Depends(get_database).

        date_string (Optional[str], optional): date string to validate. Defaults to "2021-12-12".

    Raises:

        HTTPException: Incorrect API key provided

    Returns:

        dict: of type {"isValidDate": bollean, "isValidApiKey": bollean}
    """

    if api_key != API_KEY:
        raise HTTPException(status_code=400, detail="Erreneous API key recieved.")

    print(db)

    return {"isValidDate": is_valid_date(date_string), "isValidApiKey": True}
