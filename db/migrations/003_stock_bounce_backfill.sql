CREATE TABLE IF NOT EXISTS stock_bounce_backfill_runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    report JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stock_bounce_backfill_targets (
    run_id TEXT NOT NULL REFERENCES stock_bounce_backfill_runs(run_id) ON DELETE CASCADE,
    session_date DATE NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, session_date)
);

CREATE TABLE IF NOT EXISTS stock_bounce_backfill_ranges (
    run_id TEXT NOT NULL REFERENCES stock_bounce_backfill_runs(run_id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, ticker, start_date, end_date)
);
