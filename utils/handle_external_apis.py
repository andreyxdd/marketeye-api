"""
Methods to access external endpoints and manage responses
"""

import quandl
from utils.handle_datetimes import is_valid_date, get_past_date
from utils.handle_calculations import compute_base_analytics, compute_extra_analytics
from core.settings import QUANDL_API_KEY

quandl.ApiConfig.api_key = QUANDL_API_KEY


def get_ticker_analytics(ticker: str, date: str) -> dict:
    """
    Function that returns analytics (base and extra) for a single stock
    represneted by the ticker

    Args:
        ticker (str): stock ticker, e.g. "AAPL"
        date (str): date string, at which the analytics should be evaluated

    Raises:
        Exception: Quandl databse don't have enough EOD data for the given ticker (not enough days)
        Exception: Method reported an error

    Returns:
        dict: combination of returned values from compute_base_analytics and compute_extra_analytics
    """
    try:
        is_valid_date(date)

        # offset of calendar days back in the past
        offset_n_days = 85

        # number of trading days actually needed to compute analytics
        actual_offset_n_days = 50

        offset_date = get_past_date(offset_n_days, date)

        quandl_df = quandl.get_table(
            "QUOTEMEDIA/PRICES",
            ticker=ticker,
            qopts={
                "columns": ["ticker", "date", "open", "high", "low", "close", "volume"]
            },
            date={"gte": offset_date, "lte": date},
        )

        if quandl_df.shape[0] < actual_offset_n_days:
            raise Exception(
                f"Not enough tradings days ({quandl_df.shape[0]}) for the given ticker {ticker}"
            )

        return {
            **compute_base_analytics(quandl_df),
            **compute_extra_analytics(quandl_df),
        }
    except Exception as e:
        raise Exception(
            "handle_external_apis.py, get_ticker_analytics reported an error"
        ) from e


def get_ticker_base_analytics(ticker: str, date: str) -> dict:
    """
    Function that returns only base analytics for a single stock
    represneted by the ticker

    Args:
        ticker (str): stock ticker, e.g. "AAPL"
        date (str): date string, at which the analytics should be evaluated

    Raises:
        Exception: Quandl databse don't have enough EOD data for the given ticker (not enough days)
        Exception: Method reported an error

    Returns:
        dict: see returned values from compute_base_analytics
    """
    try:
        is_valid_date(date)

        # offset of calendar days back in the past
        offset_n_days = 85

        # number of trading days actually needed to compute analytics
        actual_offset_n_days = 50

        offset_date = get_past_date(offset_n_days, date)

        quandl_df = quandl.get_table(
            "QUOTEMEDIA/PRICES",
            ticker=ticker,
            qopts={
                "columns": ["ticker", "date", "open", "high", "low", "close", "volume"]
            },
            date={"gte": offset_date, "lte": date},
        )

        if quandl_df.shape[0] < actual_offset_n_days:
            raise Exception(
                f"Not enough tradings days ({quandl_df.shape[0]}) for the given ticker {ticker}"
            )

        return compute_base_analytics(quandl_df)
    except Exception as e:
        raise Exception(
            "handle_external_apis.py, get_ticker_base_analytics reported an error"
        ) from e
