"""
 Methods to handle date-strings and datetime objects.
 The UTC timezone should be used in db by default.
 Thus, all the methods return the dates relative to UTC.
"""

from typing import Union, Optional
from datetime import datetime, timedelta
import pytz


def get_today_utc_date_in_timezone(timezone: str) -> str:
    """
    Function that constructs date-string for today UTC date relative to a specific timezone

    Args:
        timezone (str): timezone

    Returns:
        str: date-string
    """
    ist = pytz.timezone(timezone)
    return datetime.now(ist).astimezone(pytz.utc).strftime("%Y-%m-%d")


def get_array_of_past_dates(
    n_days: int,
    base_date: Optional[Union[datetime, str]] = None,
    timezone: Optional[str] = "America/New_York",
) -> list[str]:
    """
    Function to construct an array of date-strings

    Args:
        n_days (int):
            Number of dates in the resulting array
        base_date (Optional[Union[datetime, str]], optional):
            Date to start from.
            Before the array construction this value converted to UTC.
            Defaults to None and converted to today UTC.
        timezone (Optional[str], optional):
            The string represeting time zone for all dates in the array.
            Defaults to "America/New_York".

    Returns:
        list[str]: resulting array of date-strings. Fromat is YYYY-MM-DD.
    """
    if base_date is None:
        base_date = get_today_utc_date_in_timezone(timezone)

    if isinstance(base_date, str):
        base_date = datetime.strptime(base_date, "%Y-%m-%d").astimezone(pytz.utc)

    return [(base_date - timedelta(days=x)).strftime("%Y-%m-%d") for x in range(n_days)]


def get_past_date(
    n_days: int,
    base_date: Optional[Union[datetime, str]] = None,
    timezone: Optional[str] = "America/New_York",
) -> str:
    """
    Function that returns the date-string represeinting n_days ago from the base_date.

    Args:
        n_days (int):
            Number of dates in the resulting array
        base_date (Optional[Union[datetime, str]], optional):
            Date to start from.
            Before the array construction this value converted to UTC.
            Defaults to None and converted to today UTC.
        timezone (Optional[str], optional):
            The string represeting time zone for all dates in the array.
            Defaults to "America/New_York".

    Returns:
        str: date-string. Format is YYYY-MM-DD.
    """
    if base_date is None:
        base_date = get_today_utc_date_in_timezone(timezone)

    if isinstance(base_date, str):
        base_date = datetime.strptime(base_date, "%Y-%m-%d").astimezone(pytz.utc)

    return (base_date - timedelta(days=n_days)).strftime("%Y-%m-%d")


def get_future_date(
    n_days: int,
    base_date: Optional[Union[datetime, str]] = None,
    timezone: Optional[str] = "America/New_York",
) -> str:
    """
    Function that returns the date-string represeinting n_days into the future from the base_date.

    Args:
        n_days (int):
            Number of dates in the resulting array
        base_date (Optional[Union[datetime, str]], optional):
            Date to start from.
            Before the array construction this value converted to UTC.
            Defaults to None and converted to today UTC.
        timezone (Optional[str], optional):
            The string represeting time zone for all dates in the array.
            Defaults to "America/New_York".

    Returns:
        str: date-string. Format is YYYY-MM-DD.
    """
    if base_date is None:
        base_date = get_today_utc_date_in_timezone(timezone)

    if isinstance(base_date, str):
        base_date = datetime.strptime(base_date, "%Y-%m-%d").astimezone(pytz.utc)

    return (base_date + timedelta(days=n_days)).strftime("%Y-%m-%d")


def is_valid_date(date_string: str, date_format: Optional[str] = "%Y-%m-%d") -> bool:
    """
    Function to validate the date-string with the provided format.

    Args:
        date_string (str):
            date-string to validate.
        format (Optional[str], optional):
            format of the date-string to validate. Defaults to '%Y-%m-%d'.

    Raises:
        ValueError: Raise exception if not valid parameter provided.

    Returns:
        bool: valid or not
    """
    is_valid = False
    try:
        datetime.strptime(date_string, date_format)
        is_valid = True
    except Exception as e:
        raise Exception(
            "handle_datetimes.py, is_valid_date:"
            + f" Erroneus date-string provided, it should have a format of {date_format}"
        ) from e
    return is_valid


def get_epoch(date_time: Union[datetime, str]) -> int:
    """
    Function that converts datetime object or date-string
    into UNIX/epoch time relative to UTC.

    Args:
        date_time (Union[datetime,str]):
            date-string or datetime object to be converted.

    Returns:
        int: epoch integer.
    """
    if isinstance(date_time, str):
        date_time = datetime.strptime(date_time, "%Y-%m-%d")
    epoch = datetime.utcfromtimestamp(0)
    return (date_time - epoch).total_seconds() * 1000.0


def get_date_string(epoch: int) -> str:
    """
    Function that converts UTC epoch datetime (ms) into date-string.

    Args:
        epoch (int):
            UNIX/epoch representation of datetime (shoudl be in UTC format).

    Returns:
        str: date-string. Fromat is YYYY-MM-DD.
    """
    return datetime.strftime(datetime.utcfromtimestamp(epoch / 1000), "%Y-%m-%d")
