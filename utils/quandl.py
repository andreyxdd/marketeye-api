

import quandl

from typing import Optional
from utils.calc import compute_single_ticker_analytics
from utils.handle_datetimes import get_past_date

from core.settings import (
    QUANDL_API_KEY,
)

quandl.ApiConfig.api_key = QUANDL_API_KEY


def get_single_ticker_analytics(
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

    Returns:
        dict: see returned values from compute_base_analytics
    """
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

    #  Quandl database doesn't have enough EOD data for the given ticker (not enough days)
    if quandl_df.shape[0] < actual_offset_n_days:
        return {}

    return compute_single_ticker_analytics(quandl_df)


def get_quandl_tickers(date: str) -> "list(str)":
    """
    Function to get the list of all the tickers for the given date

    Args:
        date (str): date, for which to search

    Returns:
        list: list of strings (tickers' names)
    """
    response = quandl.get_table("QUOTEMEDIA/PRICES", date=date, paginate=True)
    return response["ticker"].values.tolist()
