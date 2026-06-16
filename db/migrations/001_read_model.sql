CREATE TABLE IF NOT EXISTS published_dates (
    session_date DATE NOT NULL,
    market TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (session_date, market)
);

CREATE TABLE IF NOT EXISTS published_artifacts (
    session_date DATE NOT NULL,
    market TEXT NOT NULL,
    artifact_key TEXT NOT NULL,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (session_date, market, artifact_key),
    CONSTRAINT fk_published_artifacts_date
        FOREIGN KEY (session_date, market)
        REFERENCES published_dates (session_date, market)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS published_tickers (
    session_date DATE NOT NULL,
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (session_date, market, ticker),
    CONSTRAINT fk_published_tickers_date
        FOREIGN KEY (session_date, market)
        REFERENCES published_dates (session_date, market)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_published_dates_market_date
    ON published_dates (market, session_date DESC);
