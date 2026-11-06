CREATE TABLE IF NOT EXISTS stock_bounce_v2_high_watermarks (
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    as_of_date DATE NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (market, ticker)
);

CREATE TABLE IF NOT EXISTS stock_bounce_v2_splits (
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    split_date DATE NOT NULL,
    ratio DOUBLE PRECISION NOT NULL CHECK (ratio > 0),
    PRIMARY KEY (market, ticker, split_date)
);

CREATE TABLE IF NOT EXISTS stock_bounce_v2_memberships (
    market TEXT NOT NULL,
    ticker TEXT NOT NULL,
    universe TEXT NOT NULL CHECK (universe IN ('whole_market', 'macd_history')),
    first_seen_date DATE NOT NULL,
    last_seen_date DATE NOT NULL,
    PRIMARY KEY (market, ticker, universe)
);

CREATE INDEX IF NOT EXISTS idx_stock_bounce_v2_memberships_universe_date
    ON stock_bounce_v2_memberships (market, universe, first_seen_date);

CREATE TABLE IF NOT EXISTS stock_bounce_v2_backfill_runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    report JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stock_bounce_v2_backfill_targets (
    run_id TEXT NOT NULL REFERENCES stock_bounce_v2_backfill_runs(run_id) ON DELETE CASCADE,
    session_date DATE NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, session_date)
);

CREATE TABLE IF NOT EXISTS stock_bounce_v2_backfill_ranges (
    run_id TEXT NOT NULL REFERENCES stock_bounce_v2_backfill_runs(run_id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    start_date DATE,
    end_date DATE NOT NULL,
    status TEXT NOT NULL,
    payload JSONB,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, ticker, end_date)
);

CREATE INDEX IF NOT EXISTS idx_published_artifacts_key_date
    ON published_artifacts (market, artifact_key, session_date);

CREATE INDEX IF NOT EXISTS idx_stock_bounce_v2_splits_ticker_date
    ON stock_bounce_v2_splits (market, ticker, split_date);
