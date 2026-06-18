"""
Methods to access external endpoints and manage responses
"""
import random
import time
import requests
import pandas as pd
from typing import Optional, List
from time import sleep
from pandas import date_range, json_normalize
from requests import get
from requests.exceptions import RequestException
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
    format_number_short,
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
    DEFAULT_HEADERS,
)
from core.markets import DEFAULT_MARKET, normalize_market

from providers import get_market_data_provider

nasdaqdatalink.ApiConfig.api_key = QUANDL_API_KEY

cache = RedisCache()
cache.connect()

_ticker_universe_cache: dict[tuple[str, str], list] = {}


def clear_ticker_universe_cache() -> None:
    """Clear in-process ticker universe memoization (call at cron start)."""
    _ticker_universe_cache.clear()


MI_REQUEST_TIMEOUT_SECONDS = 30
MI_MAX_ATTEMPTS = 3


def _market_insider_headers() -> dict:
    return {key: value for key, value in DEFAULT_HEADERS.items() if value}


def _market_insider_request(url: str, label: str):
    """GET Market Insider with stable headers and retry on transient failures."""
    headers = _market_insider_headers()
    last_error: Optional[Exception] = None

    for attempt in range(1, MI_MAX_ATTEMPTS + 1):
        try:
            response = get(url, headers=headers, timeout=MI_REQUEST_TIMEOUT_SECONDS)
            if response.status_code == 200:
                return response
            if response.status_code >= 500 and attempt < MI_MAX_ATTEMPTS:
                sleep(2**attempt)
                continue
            raise Exception(
                "Requests to the external data source for the market analytics failed "
                + f"with the code {response.status_code} ({label}). \nRequest string is: {url}"
            )
        except RequestException as exc:
            last_error = exc
            if attempt < MI_MAX_ATTEMPTS:
                sleep(2**attempt)
                continue
            raise Exception(
                "Requests to the external data source for the market analytics failed "
                + f"({label}). \nRequest string is: {url}"
            ) from exc

    if last_error is not None:
        raise last_error
    raise Exception(
        "Requests to the external data source for the market analytics failed "
        + f"({label}). \nRequest string is: {url}"
    )

@cache.use_cache()
def get_ticker_analytics(
    ticker: str,
    date: str,
    offset_n_days: Optional[int] = 85,
    actual_offset_n_days: Optional[int] = 50,
    test_offset: Optional[bool] = False,
    market: str = DEFAULT_MARKET,
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
        provider = get_market_data_provider(market)
        return provider.fetch_ticker_analytics(
            ticker, date, offset_n_days, actual_offset_n_days, test_offset
        )
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            "utils/handle_external_apis.py, get_ticker_analytics reported an error"
        ) from e


# @cache.use_cache()
def get_ticker_base_analytics(
    ticker: str,
    date: str,
    offset_n_days: Optional[int] = 85,
    actual_offset_n_days: Optional[int] = 50,
    to_paginate: Optional[bool] = True,
    market: str = DEFAULT_MARKET,
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
        del to_paginate
        provider = get_market_data_provider(market)
        return provider.fetch_ticker_base_analytics(
            ticker, date, offset_n_days, actual_offset_n_days
        )
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            f"utils/handle_external_apis.py, get_ticker_base_analytics reported an error for ticker {ticker} and date {date}"
        ) from e

# @cache.use_cache()
def get_ticker_extra_analytics(
    ticker: str,
    date: str,
    offset_n_days: Optional[int] = 85,
    actual_offset_n_days: Optional[int] = 50,
    test_offset: Optional[bool] = False,
    market: str = DEFAULT_MARKET,
) -> dict:
    del test_offset
    try:
        provider = get_market_data_provider(market)
        return provider.fetch_ticker_extra_analytics(
            ticker, date, offset_n_days, actual_offset_n_days
        )
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

        response = _market_insider_request(request, "S&P")

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

        response = _market_insider_request(request, "VIX")

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

def get_tickers(date: str, market: str = DEFAULT_MARKET) -> list:
    try:
        market = normalize_market(market)
        cache_key = (market, date)
        if cache_key in _ticker_universe_cache:
            return list(_ticker_universe_cache[cache_key])

        provider = get_market_data_provider(market)
        tickers = provider.fetch_ticker_universe(date)
        _ticker_universe_cache[cache_key] = tickers
        return tickers
    except Exception as e:
        print("Error message:", e)
        raise Exception(
            f"utils/handle_external_apis.py, get_tickers reported an error for market {market}"
        ) from e


def get_polygon_tickers(date: str) -> list:
    """Backward-compatible alias for US ticker universe."""
    return get_tickers(date, market="US")

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


MAX_RETRIES = 6
RETRY_BACKOFF = (15, 30)  # random sleep between 15–30 seconds

@cache.use_cache()
def get_quaterly_free_cash_flow(ticker: str, date_quater: str) -> str:
    """
    Function to get a free cash flow of the given stock ticker
    and for the given quater (represented by a date string)

    Args:
        ticker (str): ticker for which the FCF is needed
        date_quater (str): quaterly date

    Raises:
        Exception: in case of failure to access the yahoo endpoint

    Returns:
        str: string representation of the free cash flow for the given ticker and quarterly date
    """
    epoch_date_value = int(get_epoch(date_quater) / 1000)
    request_url = (
        f"{YAHOO_BASE_FCF_URL}/{ticker}?"
        "type=CannualFreeCashFlow%2CtrailingFreeCashFlow%2CquarterlyFreeCashFlow&"
        f"period1=493590046&period2={epoch_date_value}"
    )

    headers = Headers(headers=True).generate()

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(request_url, headers=headers)

            if response.status_code == 200:
                break
            elif response.status_code == 429:
                # Rate limited – inspect headers
                print("Received 429 Too Many Requests.")
                # print("Response headers:")
                # for key, value in response.headers.items():
                #     print(f"{key}: {value}")

                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    wait_time = float(retry_after)
                    print(f"def get_quaterly_free_cash_flow: retry-After header found. Waiting {wait_time} seconds...")
                else:
                    wait_time = random.uniform(*RETRY_BACKOFF)
                    print(f"def get_quaterly_free_cash_flow: no Retry-After header. Using random wait: {wait_time:.2f} seconds...")

                time.sleep(wait_time)
                continue
            else:
                raise Exception(
                    f"def get_quaterly_free_cash_flow: failed with status code {response.status_code}.\nRequest: {request_url}"
                )
        except RequestException as e:
            raise Exception(f"def get_quaterly_free_cash_flow: HTTP request failed: {e}")

    else:
        raise Exception("def get_quaterly_free_cash_flow: max retries exceeded due to repeated 429 errors.")

    result = response.json()

    timeseries = result.get("timeseries", {}).get("result", [])
    if not isinstance(timeseries, list) or not timeseries:
        return None

    for data in timeseries:
        if data.get("meta", {}).get("type", [None])[0] == "quarterlyFreeCashFlow":
            fcf_entries = data.get("quarterlyFreeCashFlow", [])
            if not isinstance(fcf_entries, list) or not fcf_entries:
                return None
            last_entry = fcf_entries[-1]
            return last_entry.get("reportedValue", {}).get("fmt", None)

    return None

def get_quarterly_free_cash_flow_polygon(ticker: str, date_quarter: str) -> str:
    url = "https://api.polygon.io/vX/reference/financials"
    params = {
        "ticker": ticker,
        "period_of_report_date.lte": date_quarter,
        "timeframe": "quarterly",
        "order": "desc",
        "limit": 1,
        "sort": "filing_date",
        "apiKey": POLYGON_API_KEY
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    try:
        results = data["results"]
        if not results:
            return "N/A"

        cash_flow = results[0]["financials"]["cash_flow_statement"]
        fcf = cash_flow["net_cash_flow_from_operating_activities"]["value"]
        return format_number_short(fcf)
    except (KeyError, IndexError, TypeError):
        return "N/A"

def cache_quaterly_free_cash_flow(tickers: List[str], date: str, rate_limit: int = 10):
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
    try:
        quater_dates = date_range(start_date, date, freq="QE")
    except ValueError:
        quater_dates = date_range(start_date, date, freq="Q")

    last_quater_limit_date = quater_dates[-1].strftime("%Y-%m-%d")
    validate_date_string(last_quater_limit_date)

    for ticker in tickers:
        sleep(rate_limit)
        get_quaterly_free_cash_flow(ticker, last_quater_limit_date)
