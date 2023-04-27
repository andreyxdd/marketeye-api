"""
 Methods to handle date-strings and datetime objects.
 The UTC timezone should be used in db by default.
 Thus, all the methods return the dates relative to UTC.
"""

from typing import Union, Optional
from datetime import datetime, timedelta
from pandas import date_range
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
) -> "list[str]":
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
        print("Error message:", e)
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


def get_market_insider_url_string(date_past: str, date_future: str) -> str:
    """
    Funciton to construct a specific string, which is a part of request to the
    external API - Market Insider data table.
    For instance, given 'datePast = 2021-11-26' and 'dateFuture = 2021-12-30' the function returns:
    Nov.%2026%202021_Dec.%2030%202021

    Args:
        date_past (str): date_string representing the start of the period
        date_future (str): date_string representing the start of the period

    Raises:
        Exception: date_past can't be higher than date_future

    Returns:
        str: part of the request string
    """
    if get_epoch(date_past) > get_epoch(date_future):
        raise Exception(
            "handle_datetimes.py, def get_market_insider_url:"
            + f"'date_past' {date_past} should not be higher than 'date_future' {date_future}"
        )

    past_date = datetime.strptime(date_past, "%Y-%m-%d")
    future_date = datetime.strptime(date_future, "%Y-%m-%d")

    past_string = (
        f"{past_date.strftime('%b')}.%20"
        + f"{past_date.strftime('%d')}%20"
        + f"{past_date.strftime('%Y')}"
    )
    future_string = (
        f"{future_date.strftime('%b')}.%20"
        + f"{future_date.strftime('%d')}%20"
        + f"{future_date.strftime('%Y')}"
    )

    return f"{past_string}_{future_string}"


def get_last_quater_date(date: str):
    """
    Method to get the date representing the last date of the previous quater

    Args:
        date (str): date string

    Returns:
        str: last date (as string) of the previous quater
    """
    start_date = get_past_date(366, date)
    quater_dates = date_range(start_date, date, freq="Q")

    last_quater_limit_date = quater_dates[-1].strftime("%Y-%m-%d")
    is_valid_date(last_quater_limit_date)

    return last_quater_limit_date
