"""Archive-first StockBounce session and result reads."""

import base64
import json
from datetime import date

from db.crud.published_archive import (
    STOCK_BOUNCE_ARTIFACT_KEY,
    get_artifact_payload,
)
from utils.handle_datetimes import get_epoch

from .semantics import evaluate, validate_snapshot


class StockBounceReadError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def _encode_cursor(date_string: str) -> str:
    return (
        base64.urlsafe_b64encode(date_string.encode("ascii"))
        .decode("ascii")
        .rstrip("=")
    )


def _decode_cursor(cursor: str) -> str:
    try:
        padding = "=" * (-len(cursor) % 4)
        value = base64.urlsafe_b64decode(cursor + padding).decode("ascii")
        date.fromisoformat(value)
        if value != date.fromisoformat(value).isoformat():
            raise ValueError("non-canonical date")
        return value
    except Exception as error:
        raise StockBounceReadError(
            422, "INVALID_CURSOR", "StockBounce cursor is invalid"
        ) from error


SCAN_ROW_BUDGET = 1000


async def list_sessions(pool, cursor=None, limit=200) -> dict:
    after = _decode_cursor(cursor) if cursor else None
    batch_size = max(limit + 1, 10)
    valid_dates = []
    scanned = 0
    records = []
    async with pool.acquire() as conn:
        while len(valid_dates) < limit + 1 and scanned < SCAN_ROW_BUDGET:
            current_batch = min(batch_size, SCAN_ROW_BUDGET - scanned)
            records = await conn.fetch(
                """
                SELECT session_date, payload
                FROM published_artifacts
                WHERE market = 'US' AND artifact_key = $1
                  AND ($2::date IS NULL OR session_date > $2::date)
                ORDER BY session_date ASC
                LIMIT $3
                """,
                STOCK_BOUNCE_ARTIFACT_KEY,
                date.fromisoformat(after) if after else None,
                current_batch,
            )
            if not records:
                break
            scanned += len(records)
            for record in records:
                snapshot = record["payload"]
                try:
                    if isinstance(snapshot, str):
                        snapshot = json.loads(snapshot)
                    validate_snapshot(snapshot)
                except (KeyError, TypeError, ValueError):
                    continue
                session_date = record["session_date"].isoformat()
                if snapshot["date"] == session_date:
                    valid_dates.append(session_date)
                    if len(valid_dates) == limit + 1:
                        break
            after = records[-1]["session_date"].isoformat()
            if len(records) < current_batch:
                break
    page = valid_dates[:limit]
    items = [
        {"epoch": get_epoch(date_string), "date_string": date_string}
        for date_string in page
    ]
    if len(valid_dates) > limit and page:
        next_cursor = _encode_cursor(page[-1])
    elif scanned >= SCAN_ROW_BUDGET and records:
        next_cursor = _encode_cursor(after)
    else:
        next_cursor = None
    return {"items": items, "next_cursor": next_cursor}


async def evaluate_session(
    pool,
    *,
    date_string: str,
    period: int,
    price_range: str = "all",
    tickers=None,
) -> dict:
    async with pool.acquire() as conn:
        known = await conn.fetchrow(
            "SELECT 1 FROM published_dates WHERE session_date = $1 AND market = 'US'",
            date.fromisoformat(date_string),
        )
    if known is None:
        raise StockBounceReadError(
            404,
            "SESSION_NOT_FOUND",
            f"US session {date_string} was not found",
        )
    snapshot = await get_artifact_payload(
        pool, date_string, STOCK_BOUNCE_ARTIFACT_KEY, market="US"
    )
    if snapshot is None:
        raise StockBounceReadError(
            409,
            "BOUNCE_SESSION_NOT_READY",
            f"StockBounce publication is incomplete for US {date_string}",
        )
    try:
        if not isinstance(snapshot, dict):
            raise ValueError("snapshot must be a JSON object")
        if snapshot.get("date") != date_string:
            raise ValueError("snapshot session date does not match artifact key")
        return evaluate(
            snapshot,
            period=period,
            price_range=price_range,
            tickers=tickers,
        )
    except ValueError as error:
        raise StockBounceReadError(
            409,
            "BOUNCE_SESSION_NOT_READY",
            f"StockBounce publication is incomplete for US {date_string}",
            {"reason": str(error)},
        ) from error


async def list_sessions_v2(pool, cursor=None, limit=200) -> dict:
    """List valid v2 artifacts with coverage derived from retained sessions."""
    from db.crud.published_archive import STOCK_BOUNCE_V2_ARTIFACT_KEY
    from .semantics_v2 import validate_snapshot_v2

    after = _decode_cursor(cursor) if cursor else None
    batch_size = max(limit + 1, 10)
    valid = []
    scanned = 0
    records = []
    async with pool.acquire() as conn:
        while len(valid) < limit + 1 and scanned < SCAN_ROW_BUDGET:
            current_batch = min(batch_size, SCAN_ROW_BUDGET - scanned)
            records = await conn.fetch(
                """
                SELECT a.session_date, a.payload,
                       LEAST(1260, (
                           SELECT COUNT(*) FROM published_artifacts prior
                           WHERE prior.market = 'US' AND prior.artifact_key = a.artifact_key
                             AND prior.session_date < a.session_date
                             AND prior.payload->>'schema_version' = '2'
                       ))::int AS supported_lookback
                FROM published_artifacts a
                WHERE a.market = 'US' AND a.artifact_key = $1
                  AND ($2::date IS NULL OR a.session_date > $2::date)
                ORDER BY a.session_date ASC
                LIMIT $3
                """,
                STOCK_BOUNCE_V2_ARTIFACT_KEY,
                date.fromisoformat(after) if after else None,
                current_batch,
            )
            if not records:
                break
            scanned += len(records)
            for record in records:
                snapshot = record["payload"]
                try:
                    if isinstance(snapshot, str):
                        snapshot = json.loads(snapshot)
                    validate_snapshot_v2(snapshot)
                    session_date = record["session_date"].isoformat()
                    if snapshot["date"] != session_date:
                        continue
                    supported = min(
                        snapshot["max_lookback"],
                        int(record["supported_lookback"]),
                    )
                    valid.append((session_date, supported))
                    if len(valid) == limit + 1:
                        break
                except (KeyError, TypeError, ValueError):
                    continue
            after = records[-1]["session_date"].isoformat()
            if len(records) < current_batch:
                break
    page = valid[:limit]
    items = [
        {
            "epoch": get_epoch(date_string),
            "date_string": date_string,
            "max_lookback": supported,
        }
        for date_string, supported in page
    ]
    if len(valid) > limit and page:
        next_cursor = _encode_cursor(page[-1][0])
    elif scanned >= SCAN_ROW_BUDGET and records:
        next_cursor = _encode_cursor(after)
    else:
        next_cursor = None
    return {"items": items, "next_cursor": next_cursor}


async def evaluate_session_v2(pool, *, date_string: str, lookback: int) -> dict:
    """Read one canonical snapshot and one bounded set of start/T-1 bars."""
    from db.crud.published_archive import STOCK_BOUNCE_V2_ARTIFACT_KEY
    from .semantics_v2 import (
        UnsupportedLookbackError,
        evaluate_v2,
        validate_snapshot_v2,
    )

    session_date = date.fromisoformat(date_string)
    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            """
            SELECT a.payload,
                   LEAST(1260, (
                       SELECT COUNT(*) FROM published_artifacts prior
                       WHERE prior.market = 'US' AND prior.artifact_key = $2
                         AND prior.session_date < d.session_date
                         AND prior.payload->>'schema_version' = '2'
                   ))::int AS supported_lookback
            FROM published_dates d
            LEFT JOIN published_artifacts a
              ON a.session_date = d.session_date AND a.market = d.market
             AND a.artifact_key = $2
            WHERE d.session_date = $1 AND d.market = 'US'
            """,
            session_date,
            STOCK_BOUNCE_V2_ARTIFACT_KEY,
        )
        if record is None:
            raise StockBounceReadError(
                404,
                "SESSION_NOT_FOUND",
                f"US session {date_string} was not found",
            )
        snapshot = record["payload"]
        if snapshot is None:
            raise StockBounceReadError(
                409,
                "BOUNCE_SESSION_NOT_READY",
                f"StockBounce v2 publication is incomplete for US {date_string}",
            )
        try:
            if isinstance(snapshot, str):
                snapshot = json.loads(snapshot)
            validate_snapshot_v2(snapshot)
            if snapshot["date"] != date_string:
                raise ValueError("snapshot session date does not match artifact key")
            supported = min(snapshot["max_lookback"], int(record["supported_lookback"]))
            if lookback > supported:
                raise UnsupportedLookbackError(lookback, supported)
            snapshot = {**snapshot, "max_lookback": supported}
            tickers = sorted({row["ticker"] for row in snapshot["rows"]})
            bars = []
            if tickers:
                bars = await conn.fetch(
                    """
                    WITH prior_sessions AS (
                        SELECT session_date
                        FROM published_artifacts
                        WHERE market = 'US' AND artifact_key = $2
                          AND session_date < $1
                          AND payload->>'schema_version' = '2'
                        ORDER BY session_date DESC
                        LIMIT $3
                    ), bounds AS (
                        SELECT
                            (SELECT session_date FROM prior_sessions
                             ORDER BY session_date ASC LIMIT 1) AS start_date,
                            (SELECT session_date FROM prior_sessions
                             ORDER BY session_date DESC LIMIT 1) AS previous_date
                    )
                    SELECT b.ticker, b.session_date, b.open, b.close,
                           bounds.start_date, bounds.previous_date
                    FROM ohlcv_bars b
                    CROSS JOIN bounds
                    WHERE b.market = 'US' AND b.ticker = ANY($4::text[])
                      AND b.session_date IN (bounds.start_date, bounds.previous_date)
                    ORDER BY b.ticker, b.session_date
                    """,
                    session_date,
                    STOCK_BOUNCE_V2_ARTIFACT_KEY,
                    lookback,
                    tickers,
                )
            has_bounds = bool(bars) and "start_date" in bars[0].keys()
            return evaluate_v2(
                snapshot,
                bars,
                lookback=lookback,
                start_date=bars[0]["start_date"] if has_bounds else None,
                previous_date=bars[0]["previous_date"] if has_bounds else None,
            )
        except UnsupportedLookbackError as error:
            raise StockBounceReadError(
                422,
                "INVALID_LOOKBACK",
                "lookback exceeds the session's supported coverage",
                {"lookback": lookback, "max_lookback": error.max_lookback},
            ) from error
        except (KeyError, TypeError, ValueError) as error:
            raise StockBounceReadError(
                409,
                "BOUNCE_SESSION_NOT_READY",
                f"StockBounce v2 history is incomplete for US {date_string}",
                {"reason": str(error)},
            ) from error
