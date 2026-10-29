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
    return base64.urlsafe_b64encode(date_string.encode("ascii")).decode("ascii").rstrip("=")


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


async def list_sessions(pool, cursor=None, limit=200) -> dict:
    after = _decode_cursor(cursor) if cursor else None
    batch_size = max(limit + 1, 10)
    valid_dates = []
    async with pool.acquire() as conn:
        while len(valid_dates) < limit + 1:
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
                batch_size,
            )
            if not records:
                break
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
            if len(records) < batch_size:
                break
    page = valid_dates[:limit]
    items = [
        {"epoch": get_epoch(date_string), "date_string": date_string}
        for date_string in page
    ]
    next_cursor = (
        _encode_cursor(page[-1]) if len(valid_dates) > limit and page else None
    )
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
