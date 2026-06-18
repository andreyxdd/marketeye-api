CREATE TABLE IF NOT EXISTS ohlcv_bars (
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    session_date DATE NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume BIGINT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (market, ticker, session_date)
);

CREATE INDEX IF NOT EXISTS idx_ohlcv_bars_window
    ON ohlcv_bars (market, ticker, session_date DESC);

CREATE INDEX IF NOT EXISTS idx_ohlcv_bars_session_date
    ON ohlcv_bars (session_date);
