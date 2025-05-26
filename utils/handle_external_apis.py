"""
Methods to access external endpoints and manage responses
"""
import time
import requests
import pandas as pd
from typing import Optional, List
from time import sleep
from pandas import date_range, json_normalize
from requests import get
import nasdaqdatalink
from fake_headers import Headers
from db.redis import RedisCache
from utils.handle_validation import validate_date_string
from utils.handle_datetimes import (
    get_epoch,
    get_past_date,
    get_market_insider_url_string,
)
from utils.handle_calculations import (
    compute_base_analytics,
    compute_extra_analytics,
    get_ema_n,
)
from core.settings import (
    POLYGON_API_KEY,
    QUANDL_API_KEY,
    MI_BASE_URL,
    MI_SP500_CODE,
    MI_SP500_DATASET,
    MI_VIX_CODE,
    MI_VIX_DATASET,
    YAHOO_BASE_FCF_URL,
)

nasdaqdatalink.ApiConfig.api_key = QUANDL_API_KEY

cache = RedisCache()
cache.connect()

@cache.use_cache()
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
        end_date = pd.to_datetime(date)
        start_date = end_date - pd.Timedelta(days=offset_n_days)

        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{ticker.upper()}/range/1/day/"
            f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
            f"?adjusted=true&sort=desc&limit=50000&apiKey={POLYGON_API_KEY}"
        )

        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        if not results or len(results) < actual_offset_n_days:
            print(f"utils/handle_external_apis.py, get_ticker_analytics: not enough EOD records ({len(results)}) for ticker {ticker}")
            return {}

        df = pd.DataFrame(results)
        df["date"] = pd.to_datetime(df["t"], unit='ms').dt.strftime('%Y-%m-%d')
        df = df.rename(columns={
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume"
        })
        df = df[["date", "open", "high", "low", "close", "volume"]]
        df["ticker"] = ticker.upper()

        return {
            **compute_base_analytics(df),
            **compute_extra_analytics(df),
        }
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "utils/handle_external_apis.py, get_ticker_analytics reported an error"
        ) from e


@cache.use_cache()
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
        print(f"[DEBUG] get_ticker_base_analytics {ticker}")
        end_date = pd.to_datetime(date)
        start_date = end_date - pd.Timedelta(days=offset_n_days)

        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{ticker.upper()}/range/1/day/"
            f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
            f"?adjusted=true&sort=desc&limit=50000&apiKey=72jmDpkw2fWdiZ7hRjqUYAUxxpxdp3BK"
        )

        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        if not results or len(results) < actual_offset_n_days:
            print(f"utils/handle_external_apis.py, get_ticker_base_analytics: not enough EOD records ({len(results)}) for ticker {ticker}")
            return {}

        df = pd.DataFrame(results)
        df["t"] = pd.to_datetime(df["t"], unit='ms', utc=True)
        df = df.rename(columns={
            "t": "date",
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume"
        })
        df = df[["date", "open", "high", "low", "close", "volume"]]
        df["ticker"] = ticker.upper()

        return compute_base_analytics(df)
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            f"utils/handle_external_apis.py, get_ticker_base_analytics reported an error for ticker {ticker} and date {date}"
        ) from e

@cache.use_cache()
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
        end_date = pd.to_datetime(date)
        start_date = end_date - pd.Timedelta(days=offset_n_days)

        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{ticker.upper()}/range/1/day/"
            f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
            f"?adjusted=true&sort=desc&limit=50000&apiKey={POLYGON_API_KEY}"
        )

        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        if not results or len(results) < actual_offset_n_days:
            print(f"utils/handle_external_apis.py, get_ticker_extra_analytics: not enough EOD records ({len(results)}) for ticker {ticker}")
            return {}

        df = pd.DataFrame(results)
        df["date"] = pd.to_datetime(df["t"], unit='ms').dt.strftime('%Y-%m-%d')
        df = df.rename(columns={
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume"
        })
        df = df[["date", "open", "high", "low", "close", "volume"]]
        df["ticker"] = ticker.upper()

        return compute_extra_analytics(df)
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "utils/handle_external_apis.py, get_ticker_extra_analytics reported an error"
        ) from e


@cache.use_cache()
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

        response = get(request, headers=Headers(headers=True).generate())

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


@cache.use_cache()
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

        response = get(request, headers=Headers(headers=True).generate())

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

def get_polygon_tickers(date: str) -> list:
    """
    Function to get the list of all currently available tickers from Polygon.io

    Args:
        date (str): date, for which to search

    Raises:
        Exception: Method reported an error

    Returns:
        list: List of strings (tickers' symbols)
    """
    try:
        url = f"https://api.polygon.io/v3/reference/tickers?market=stocks&active=true&apiKey={POLYGON_API_KEY}&limit=1000&date={date}"
        tickers = []
        backoff = 1  # initial backoff in seconds

        while url:
            response = requests.get(url)
            if response.status_code == 429:
                print(f"utils/handle_external_apis.py, def get_polygon_tickers: Rate limit hit. Sleeping for {backoff} seconds...")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)  # exponential backoff capped at 60 seconds
                continue
            response.raise_for_status()

            data = response.json()
            tickers.extend([item['ticker'] for item in data.get("results", [])])

            url = data.get("next_url")
            if url:
                url += f"&apiKey={POLYGON_API_KEY}"
            backoff = 1  # reset backoff after successful request

        return tickers

    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "utils/handle_external_apis.py, def get_polygon_tickers reported an error"
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
        response = nasdaqdatalink.get_table("QUOTEMEDIA/PRICES", date=date, paginate=True)
        return response["ticker"].values.tolist()
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "utils/handle_external_apis.py, def get_quandl_tickers reported an error"
        ) from e


@cache.use_cache()
def get_quaterly_free_cash_flow(  # pylint: disable=R0911
    ticker: str, date_quater: str
) -> str:
    """
    Function to get a free cash flow of the given stock ticker
    and for the given quater (represented by a date string)

    Args:
        ticker (str): ticker for which the FCF is needed
        date_quater (str): quaterly date

    Raises:
        Exception: in case of failure to acces the yahoo endpoint

    Returns:
        str: string represntation of the free cash flow for the given ticker and quaterly date
    """
    epoch_date_value = int(get_epoch(date_quater) / 1000)
    request = (
        f"{YAHOO_BASE_FCF_URL}/"
        + f"{ticker}?"
        + "type=CannualFreeCashFlow%2CtrailingFreeCashFlow%2CquarterlyFreeCashFlow&"
        + f"&period1=493590046&period2={epoch_date_value}"
    )

    response = get(request, headers=Headers(headers=True).generate())

    if response.status_code != 200:
        raise Exception(
            "Requests to the external data source for the market analytics failed"
            + f"with the code {response.status_code} (quaterly free cash flow)."
            + f"\nRequest string is: {request}"
        )

    result = response.json()

    if "timeseries" not in result:
        return None

    result = result["timeseries"]
    if "result" not in result:
        return None

    result = result["result"]
    if not isinstance(result, list):
        return None

    if not result:
        return None

    for data in result:
        if data["meta"]["type"][0] == "quarterlyFreeCashFlow":
            result = data
            break

    if "quarterlyFreeCashFlow" not in result:
        return None

    result = result["quarterlyFreeCashFlow"]
    if not isinstance(result, list):
        return None

    if not result:
        return None

    result = result[-1]
    if "reportedValue" not in result:
        return None

    result = result["reportedValue"]
    if "fmt" not in result:
        return None

    return result["fmt"]


def cache_quaterly_free_cash_flow(tickers: List[str], date: str, rate_limit: int = 2):
    """
    Utility function to cache (in Redis) a result of
    the call to def get_quaterly_free_cash_flow

    Args:
        tickers (list[str]): list of tickers fo which the FCF needs to be cached
        date (str): reqeusted date
        rate_limit (int, optional):
            number of seconds to wait before calling get_quaterly_free_cash_flow.
            Defaults to 2.
    """
    start_date = get_past_date(366, date)
    quater_dates = date_range(start_date, date, freq="Q")

    last_quater_limit_date = quater_dates[-1].strftime("%Y-%m-%d")
    validate_date_string(last_quater_limit_date)

    for ticker in tickers:
        sleep(rate_limit)
        get_quaterly_free_cash_flow(ticker, last_quater_limit_date)
