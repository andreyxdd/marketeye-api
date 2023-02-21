"""
Utilities methods to validate API calls
"""

from fastapi import Query
from fastapi.exceptions import HTTPException
from core.settings import API_KEY
from utils.handle_datetimes import is_valid_date


def validate_api_key(
    api_key: str = Query(
        default=None,
        description="Key to check request's access status",
    )
):
    """
    Method to validate the request API key
    """
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Erreneous API key recieved.")


def validate_date_string(
    date: str = Query(
        default=None,
        description="Request data for the given date (format of YYYY-MM-DD)",
    ),
):
    """
    Method to validate the request date string
    """
    try:
        is_valid_date(date)
    except Exception as error:
        raise HTTPException(
            status_code=422,
            detail="Erroneus date-string provided, it should have a format of YYYY-MM-DD",
        ) from error

    return date


def validate_bounce_period(
    period: int = Query(
        default=None,
        description="""Number of past periods to include in the bounce analysis.
        This number should lie within the range from 1 to 18.""",
    ),
):
    """
    Method to validate the bounce period (number of days)
    """
    if period not in range(1, 19):
        raise HTTPException(status_code=422, detail="No such period implemented.")

    return period
