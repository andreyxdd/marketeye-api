"""
Methods to calculate individual stock and market-as-a-whole indicators
based on the histroical EOD data
"""
from typing import Optional
from json import loads
from pandas import DataFrame, concat
from numpy import where, exp
from scipy.stats import linregress


def get_ema_n(series, period):
    """
    Helper function to get EMA for the provided data array over the given period

    Args:
        dataArray (pandas.dataseries): usually data-array of EOD prices
        period (int): n-days period

    Returns:
        pandas.dataseries: array of ema prices over n-days period
    """
    return series.ewm(span=period, adjust=False).mean()


def compute_base_analytics(df):
    """
    Function to assemble the json object with the base analytical characteristics
    (which supposed to be inserted into db) for a single stock.

    Args:
        df (pandas.dataframe):
            dataframe with EOD data for a single stock.
            The columns are: ticker, date, volume, close, open, low, and hight (prices)

    Returns:
        dict: dictionary with the fields:
        ticker, date, macd, one_day_avg_mf, three_day_avg_mf, last_day_open_close_change,
        volume, three_day_avg_volume
    """

    # making sure the last row in dataframe coincides with the first date in the past period
    df.sort_values(by="date")

    # MACD
    macd = DataFrame(get_ema_n(df["close"], 12) - get_ema_n(df["close"], 26)).rename(
        columns={"close": "macd"}
    )

    # average EOD money flow
    one_day_avg_mf = DataFrame(
        df["volume"] * df[["close", "high", "low"]].mean(axis=1)
    ).rename(columns={0: "one_day_avg_mf"})

    # 3 day average of the average EOD money flow
    three_day_avg_mf = DataFrame(
        one_day_avg_mf["one_day_avg_mf"].rolling(3).mean()
    ).rename(columns={"one_day_avg_mf": "three_day_avg_mf"})

    # the last tradings day change between open and close prices (in fractions)
    one_day_open_close_change = DataFrame(
        df[["open", "close"]].pct_change(axis=1)["close"]
    ).rename(columns={"close": "one_day_open_close_change"})

    # 3 day average volume
    three_day_avg_volume = DataFrame(df["volume"].rolling(3).mean()).rename(
        columns={"volume": "three_day_avg_volume"}
    )

    # assembling the final dataframe
    frames = [
        df["ticker"],
        df["date"],
        macd,
        one_day_avg_mf,
        three_day_avg_mf,
        one_day_open_close_change,
        df["volume"],
        three_day_avg_volume,
    ]

    # converting to json only the last day (-last row) data and converting NaNs to zeros
    return loads(concat(frames, join="inner", axis=1).fillna(0).iloc[-1].to_json())


def compute_extra_analytics(df, n_trading_days: Optional[int] = 15):
    """
    Function to assemble the json object with the extra analytical characteristics
    (which NOT supposed to be inserted into db) for a single stock.

    Args:
        df (pandas.dataframe):
            dataframe with EOD data for a single stock.
            The columns are: ticker, date, volume, close, open, low, and hight (prices)
        nTradingDays (Optional[int], optional): [description]. Defaults to 15.

    Returns:
        [type]: [description]
    """

    # making sure the last row in dataframe coincides with the first date in the past period
    df.sort_values(by="date")

    # last day volume change in fractions
    one_day_volume_change = DataFrame(df[["volume"]].pct_change()["volume"]).rename(
        columns={"volume": "one_day_volume_change"}
    )

    # 3 day average volume  change compared to the 4th day in fractions
    df["three_day_avg_mf"] = df["volume"].rolling(3).mean()
    df["shifted_volume"] = df["volume"].shift(
        3
    )  # shifting 3 rows up to compare the 4th day with the 3-day average volume
    three_day_avg_volume_change = DataFrame(
        df[["shifted_volume", "three_day_avg_mf"]].pct_change(axis=1)[
            "three_day_avg_mf"
        ]
    ).rename(columns={"three_day_avg_mf": "three_day_avg_volume_change"})

    # last day closing price change in fractions
    one_day_close_change = DataFrame(df[["close"]].pct_change()["close"]).rename(
        columns={"close": "one_day_close_change"}
    )

    # 3 day average close price change compared to the 4th day
    df["three_day_avg_close"] = df["close"].rolling(3).mean()
    df["shifted_close"] = df["close"].shift(
        3
    )  # shifting 3 rows up to compare the 4th day with the 3-day average close price
    three_day_avg_close_change = DataFrame(
        df[["shifted_close", "three_day_avg_close"]].pct_change(axis=1)[
            "three_day_avg_close"
        ]
    ).rename(columns={"three_day_avg_close": "three_day_avg_close_change"})

    # closing price EMAs as numpy arrays
    ema3 = get_ema_n(df["close"], 3).to_numpy()
    ema9 = get_ema_n(df["close"], 9).to_numpy()
    ema12 = get_ema_n(df["close"], 12).to_numpy()
    ema20 = get_ema_n(df["close"], 20).to_numpy()
    ema26 = get_ema_n(df["close"], 26).to_numpy()
    ema50 = get_ema_n(df["close"], 50).to_numpy()

    # closing prices change between days for the 3-day period (in fractions)
    dyas12_close_change = (df["close"].iloc[-1] - df["close"].iloc[-2]) / df[
        "close"
    ].iloc[-2]
    dyas23_close_change = (df["close"].iloc[-2] - df["close"].iloc[-3]) / df[
        "close"
    ].iloc[-3]

    # for comupting money flow ratio
    typical_price = DataFrame(df[["close", "high", "low"]].mean(axis=1)).rename(
        columns={0: "typical"}
    )

    # if a stock does not have a data for the last 14 days, use the availble period instead
    if len(typical_price["typical"]) - 1 < n_trading_days:
        n_trading_days = len(typical_price["typical"]) - 1

    return {
        # assembling new dataframe and converting to json only the
        # last day (last row) data and converting NaNs to zeros
        **loads(
            concat(
                [
                    df["ticker"],
                    df["date"],
                    df["volume"],
                    one_day_volume_change,
                    three_day_avg_volume_change,
                    one_day_close_change,
                    three_day_avg_close_change,
                ],
                join="inner",
                axis=1,
            )
            .fillna(0)
            .iloc[-1]
            .to_json()
        ),
        # comparing EMAs for diffrent periods over the three last days
        # e.g. ema3 is higher than ema9 for the last three days (inlcuding last day in the period?)
        # reversion arrays afterwards so that last day is on the first index
        "ema_3over9": where(ema3[-3:] > ema9[-3:], "A", "B").tolist()[::-1],
        "ema_12over9": where(ema12[-3:] > ema9[-3:], "A", "B").tolist()[::-1],
        "ema_12over26": where(ema12[-3:] > ema26[-3:], "A", "B").tolist()[::-1],
        "ema_50over20": where(ema50[-3:] > ema20[-3:], "A", "B").tolist()[::-1],
        "closingPriceChangeDay12": dyas12_close_change,
        "closingPriceChangeDay23": dyas23_close_change,
        "mfi": get_money_flow_index(
            typical_price["typical"], df["volume"], n_trading_days
        ),
        "ema3": ema3,
        "ema9": ema9,
        "ema12": ema12,
        "ema20": ema20,
        "ema26": ema26,
        "ema50": ema50,
    }


def get_money_flow_ratio(typical_prices, volumes, n_days) -> float:
    """
    Function to compute MFR (money flow ratio)

    Args:
        typical_prices (pandas.dataseries): typical prices data series
        volumes (pandas.dataseries): volume data series
        n_days (int): the period, over which to compute the MFI

    Returns:
        float: MFR
    """

    positive_mf = 0
    negative_mf = 10e-5  # can't divide by zero

    # getting typical price 15 days ago
    typical_price_before_period = typical_prices.iloc[n_days]  # the last row

    # computing positive and negative money flow
    for i in range(n_days):
        current_typical_price = typical_prices.iloc[-(i + 1)]  # previous to the last
        raw_mf = current_typical_price * volumes.iloc[-(i + 1)]
        if current_typical_price > typical_price_before_period[-i]:
            positive_mf += raw_mf
        else:
            negative_mf += raw_mf

    return positive_mf / negative_mf


def get_money_flow_index(typical_prices, volumes, n_days) -> float:
    """
    Function to compute Money Flow Index
    (see https://www.investopedia.com/terms/m/mfi.asp for details)

    Args:
        typical_prices (pandas.dataseries): typical prices data series
        volumes (pandas.dataseries): volume data series
        n_days (int): the period, over which to compute the MFI

    Returns:
        float: MFI
    """
    return 100 - 100 / (1 + get_money_flow_ratio(typical_prices, volumes, n_days))


def get_slope_normalized(array_x: list[float], array_y: list[float]) -> float:
    """
    Function to appxoimate the slope for the dependant arrays X and Y
    normalzied in the range from 0.0 to 1.0

    Args:
        array_x (list[float]): numerical array lying on the X-axis
        array_y (list[float]): numerical array lying on the Y-axis

    Raises:
        Exception: Incorrect sizes

    Returns:
        float: fraction of the slope. Less than 0.5 - negative slope, higher - positive
    """

    if len(array_x) != len(array_y):
        raise Exception("Passed arrays hould be of the same size")

    # converting array to pandas.dataframe to normalize them
    df = DataFrame(array_y, columns=["x"])
    df["y"] = DataFrame(array_y)
    normalized_df = (df - df.min()) / (df.max() - df.min())

    # linear regression object
    lin_reg_result = linregress(normalized_df["x"], normalized_df["y"])

    return 1 / (1 + exp(-lin_reg_result.slope))  # computing fraction
