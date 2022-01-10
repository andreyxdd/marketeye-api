"""
Methods to access external endpoints and manage responses
"""
from typing import Optional
from pandas import json_normalize
from requests import get
import quandl
from utils.handle_datetimes import (
    get_date_string,
    get_past_date,
    get_market_insider_url_string,
)
from utils.handle_calculations import (
    compute_base_analytics,
    compute_extra_analytics,
    get_ema_n,
)
from core.settings import (
    QUANDL_API_KEY,
    DEFAULT_HEADERS,
    MI_BASE_URL,
    MI_SP500_CODE,
    MI_SP500_DATASET,
    MI_VIX_CODE,
    MI_VIX_DATASET,
)

quandl.ApiConfig.api_key = QUANDL_API_KEY


def get_ticker_analytics(
    ticker: str,
    date: str,
    offset_n_days: Optional[int] = 85,
    actual_offset_n_days: Optional[int] = 50,
    test_offset: Optional[bool] = False,
) -> dict:
    """
    Function that returns analytics (base and extra) for a single stock
    represneted by the ticker. If Quandl databse don't have enough EOD
    data for the given ticker (not enough actural days), the empty
    dictionary is returned.

    Args:
        ticker (str):
            stock ticker, e.g. "AAPL"
        date (str):
            date string, at which the analytics should be evaluated
        offset_n_days (Optional[int], optional):
            offset of calendar days back in the past. Defaults to 85.
        actual_offset_n_days (Optional[int], optional):
            number of trading days actually needed to compute analytics. Defaults to 50.
        test_offset (Optional[bool], optional):
            Boolean to check if Quandl API has enough EOD records
            for the actual_offset_n_days. Defaults to False.

    Raises:
        Exception: Method reported an error

    Returns:
        dict: combination of returned values from compute_base_analytics and compute_extra_analytics
    """
    try:

        offset_date = get_past_date(offset_n_days, date)

        quandl_df = quandl.get_table(
            "QUOTEMEDIA/PRICES",
            ticker=ticker,
            qopts={
                "columns": ["ticker", "date", "open", "high", "low", "close", "volume"]
            },
            date={"gte": offset_date, "lte": date},
        )

        if test_offset and quandl_df.shape[0] < actual_offset_n_days:
            print(
                f"Not enough EOD records ({quandl_df.shape[0]}) for the given ticker {ticker}"
            )
            return {}

        return {
            **compute_base_analytics(quandl_df),
            **compute_extra_analytics(quandl_df),
        }
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "utils/handle_external_apis.py, get_ticker_analytics reported an error"
        ) from e


def get_ticker_base_analytics(
    ticker: str,
    date: str,
    offset_n_days: Optional[int] = 45,
    actual_offset_n_days: Optional[int] = 15,
    to_paginate: Optional[bool] = True,
) -> dict:
    """
    Function that returns only base analytics for a single stock
    represneted by the ticker. If Quandl databse don't have enough EOD
    data for the given ticker (not enough actural days), the empty
    dictionary is returned.

    Args:
        ticker (str):
            stock ticker, e.g. "GOOGL"
        date (str):
            date string, at which the analytics should be evaluated
        offset_n_days (Optional[int], optional):
            offset of calendar days back in the past.
            Defaults to 365 (full year).
        actual_offset_n_days (Optional[int], optional):
            number of trading days actually needed for stock to
            be included in the analytics collection.
            Defaults to 200 (approximately days in full year without weekends).
        to_paginate (Optional[bool], optional):
            bool to allow a pagination when making API call to Quandl. Defaults to True.

    Raises:
        Exception: Method reported an error

    Returns:
        dict: see returned values from compute_base_analytics
    """
    try:
        offset_date = get_past_date(offset_n_days, date)

        quandl_df = quandl.get_table(
            "QUOTEMEDIA/PRICES",
            ticker=ticker,
            qopts={
                "columns": ["ticker", "date", "open", "high", "low", "close", "volume"]
            },
            date={"gte": offset_date, "lte": date},
            paginate=to_paginate,
        )

        #  Quandl database don't have enough EOD data for the given ticker (not enough days)
        if quandl_df.shape[0] < actual_offset_n_days:
            # print(f"Not enough EOD records ({quandl_df.shape[0]}) for the given ticker {ticker}")
            return {}

        return compute_base_analytics(quandl_df)
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "utils/handle_external_apis.py, get_ticker_base_analytics reported an error"
        ) from e


def get_ticker_extra_analytics(
    ticker: str,
    date: str,
    offset_n_days: Optional[int] = 85,
    actual_offset_n_days: Optional[int] = 50,
    test_offset: Optional[bool] = False,
) -> dict:
    """
    Function that returns extra analytics for a single stock
    represneted by the ticker. If Quandl databse don't have enough EOD
    data for the given ticker (not enough actural days), the empty
    dictionary is returned.

    Args:
        ticker (str):
            stock ticker, e.g. "TSLA"
        date (str):
            date string, at which the analytics should be evaluated
        offset_n_days (Optional[int], optional):
            offset of calendar days back in the past. Defaults to 85.
        actual_offset_n_days (Optional[int], optional):
            number of trading days actually needed to compute analytics. Defaults to 50.
        test_offset (Optional[bool], optional):
            Boolean to check if Quandl API has enough EOD records
            for the actual_offset_n_days. Defaults to False.

    Raises:
        Exception: Method reported an error

    Returns:
        dict: see output for compute_extra_analytics
    """
    try:

        offset_date = get_past_date(offset_n_days, date)

        quandl_df = quandl.get_table(
            "QUOTEMEDIA/PRICES",
            ticker=ticker,
            qopts={
                "columns": ["ticker", "date", "open", "high", "low", "close", "volume"]
            },
            date={"gte": offset_date, "lte": date},
        )

        if test_offset and quandl_df.shape[0] < actual_offset_n_days:
            print(
                f"Not enough EOD records ({quandl_df.shape[0]}) for the given ticker {ticker}"
            )
            return {}

        return compute_extra_analytics(quandl_df)
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "utils/handle_external_apis.py, get_ticker_extra_analytics reported an error"
        ) from e


def get_market_sp500(date: str, actual_offset_n_days: Optional[int] = 50):
    """
    Function to obtain market S&P 500 for the provided date

    Args:
        date (str): date string
        actual_offset_n_days (Optional[int], optional):
            Offset date is needed for the request. Defaults to 1.

    Raises:
        Exception: Request returned error
        Exception: Method reported an error

    Returns:
        float: Given date's market's S&P500
    """
    try:
        offset_date = get_past_date(actual_offset_n_days, date)

        request = (
            f"{MI_BASE_URL}/"
            + f"{MI_SP500_CODE}/"
            + f"{get_market_insider_url_string(offset_date, date)}/"
            + f"{MI_SP500_DATASET}"
        )

        response = get(request, headers=DEFAULT_HEADERS)

        if response.status_code != 200:
            raise Exception(
                "Requests to the external data source for the market analytics failed"
                + f"with the code {response.status_code} (S&P). \nRequest string is: {request}"
            )

        return response.json()[0]["Close"]  # only value for the provided date
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "utils/handle_external_apis.py, def get_market_sp500 reported an error"
        ) from e


def get_market_vixs(
    date: str,
    offset_n_days: Optional[int] = 85,
    actual_offset_n_days: Optional[int] = 50,
):
    """
    Function to obtain market Cboe Volatility Index for the given date, the day before,
    two day before, and past 50-day average (EMA)

    Args:
        date (str): date string
        offset_n_days (Optional[int], optional): calendar days offset (including weekends)
        actual_offset_n_days (Optional[int], optional):
            Total number of dates to calculate average vix. Defaults to 50.

    Raises:
        Exception: Request returned error
        Exception: Method reported an error

    Returns:
        dict: {
            VIX - for the given date,
            VIX1 - the day before,
            VIX2 - 2 days before,
            VIX_50days_EMA - 50-day average
        }
    """
    try:
        offset_date = get_past_date(offset_n_days, date)

        request = (
            f"{MI_BASE_URL}/"
            + f"{MI_VIX_CODE}/"
            + f"{get_market_insider_url_string(offset_date, date)}/"
            + f"{MI_VIX_DATASET}"
        )

        response = get(request, headers=DEFAULT_HEADERS)

        if response.status_code != 200:
            raise Exception(
                "Requests to the external data source for the market analytics failed"
                + f"with the code {response.status_code} (VIX). \nRequest string is: {request}"
            )

        # getting VIXs and n-trading days average (- actualOffset)
        json_response = response.json()

        return {
            "VIX": json_response[0]["Close"],
            "VIX1": json_response[1]["Close"],
            "VIX2": json_response[2]["Close"],
            "VIX_50days_EMA": get_ema_n(
                json_normalize(json_response)["Close"].iloc[::-1],
                actual_offset_n_days,
            )[
                0
            ],  # reversing the dataseries and getting the first-row value
        }
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "utils/handle_external_apis.py, def get_market_vixs reported an error"
        ) from e


def get_quandl_tickers(date: str):
    """
    Function to get the list of all the tickers for the given date

    Args:
        date (str): date, for which to search

    Raises:
        Exception: Method reported an error

    Returns:
        list: list of strings (tickers' names)
    """
    try:
        response = quandl.get_table("QUOTEMEDIA/PRICES", date=date, paginate=True)
        return response["ticker"].values.tolist()
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "utils/handle_external_apis.py, def get_quandl_tickers reported an error"
        ) from e


def extend_base_analytics(base_analytics: dict):
    """
    Function that extends the provided base_analytics object (see
    output schema for the compute_base_analytics) with extra_analytics
    object (see output schema for the compute_extra_analytics)

    Args:
        base_analytics (dict): see output schema for the compute_base_analytics

    Raises:
        Exception: Method reported an error

    Returns:
        dict: combination of returned values from compute_base_analytics and compute_extra_analytics
    """
    try:
        return {
            **base_analytics,
            **get_ticker_extra_analytics(
                base_analytics["ticker"], get_date_string(base_analytics["date"])
            ),
        }
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "utils/handle_external_apis.py, def extend_base_analytics reported an error"
        ) from e
