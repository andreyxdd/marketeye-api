ANALYTICS_CRITERIA = [
    "one_day_avg_mf",
    "three_day_avg_mf",
    "volume",
    "three_day_avg_volume",
    "macd",
]

# touples describe limits put on the EOD closing price
BOUNCE_CRITERIA = [
    "unlimited",
    (48.0, 99.99),
    (100.0, 299.99),
    (300.0, 499.99),
    (500.0, 1000.0),
]

N_FREQUENCY_PERIODS = 5

N_BOUNCE_PERIODS = N_FREQUENCY_PERIODS
