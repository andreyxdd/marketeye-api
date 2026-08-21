#!/usr/bin/env python3
"""Entitlement spike: EODHD All-in-One US (lists, EOD, fundamentals OCF).

Loads EODHD_API_KEY from env or nearest .env (worktree / repo root).
If key missing, prints skip reason and exits 0 (script still present for CI/docs).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent if ROOT.parent.name == ".worktrees" else ROOT


def _load_key() -> str | None:
    key = os.getenv("EODHD_API_KEY")
    if key:
        return key.strip().strip('"').strip("'")
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None
    for path in (ROOT / ".env", REPO_ROOT / ".env"):
        if path.is_file() and load_dotenv is not None:
            load_dotenv(path, override=False)
            key = os.getenv("EODHD_API_KEY")
            if key:
                return key.strip().strip('"').strip("'")
    return None


BASE = "https://eodhd.com/api"


def main() -> int:
    api_key = _load_key()
    if not api_key:
        print(
            "skip: EODHD_API_KEY missing — set env or .env; "
            "script exists for entitlement check when key available"
        )
        print("lists=skip eod=skip fundamentals=skip")
        return 0

    session = requests.Session()
    ok = {"lists": False, "eod": False, "fundamentals": False}

    # NYSE + NASDAQ lists
    for exchange in ("NYSE", "NASDAQ"):
        url = f"{BASE}/exchange-symbol-list/{exchange}?api_token={api_key}&fmt=json"
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or len(data) < 10:
            raise SystemExit(f"lists fail: {exchange} returned {type(data)} len={len(data) if isinstance(data, list) else 'n/a'}")
    ok["lists"] = True

    # AAPL.US EOD window
    url = (
        f"{BASE}/eod/AAPL.US?from=2024-01-01&to=2024-06-03"
        f"&period=d&fmt=json&api_token={api_key}"
    )
    resp = session.get(url, timeout=60)
    resp.raise_for_status()
    bars = resp.json()
    if not isinstance(bars, list) or len(bars) < 20:
        raise SystemExit(f"eod fail: got {len(bars) if isinstance(bars, list) else bars}")
    ok["eod"] = True

    # Fundamentals OCF
    url = (
        f"{BASE}/fundamentals/AAPL.US"
        f"?api_token={api_key}&fmt=json&filter=Financials::Cash_Flow::quarterly"
    )
    resp = session.get(url, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    quarterly = payload
    if isinstance(payload, dict) and "totalCashFromOperatingActivities" not in str(payload)[:200]:
        # filter may return nested or flat quarterly dict
        quarterly = (
            payload.get("quarterly")
            or payload.get("Cash_Flow", {}).get("quarterly")
            or payload
        )
    if not isinstance(quarterly, dict) or not quarterly:
        raise SystemExit(f"fundamentals fail: unexpected shape {type(payload)}")
    sample = next(iter(quarterly.values()))
    ocf = sample.get("totalCashFromOperatingActivities")
    if ocf is None:
        raise SystemExit(f"fundamentals fail: no OCF in sample {sample}")
    ok["fundamentals"] = True

    print(
        f"lists={'ok' if ok['lists'] else 'fail'} "
        f"eod={'ok' if ok['eod'] else 'fail'} "
        f"fundamentals={'ok' if ok['fundamentals'] else 'fail'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
