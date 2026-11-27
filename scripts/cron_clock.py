"""Heroku clock dyno: run probe -> cronjob at fixed UTC slots, forever."""

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE_TIMEOUT_S = 300
# A nightly run takes ~10 min. On timeout the child gets SIGKILL: no cron report, but the lock
# dies with its connection and ingest skips stored tickers, so the next slot resumes.
# Raise this if backfills need longer.
CRONJOB_TIMEOUT_S = 60 * 60

DEFAULT_SLOTS = (
    "20:07,20:37,21:07,21:37,22:07,22:37,23:07,23:37,"
    "00:07,00:37,01:07,01:37,02:07,02:37,03:07"
)


def parse_slots(raw: str) -> list:
    """Parse comma-separated `HH:MM` (UTC) into [(hour, minute)]; ValueError if malformed."""
    slots = []
    for part in raw.split(","):
        hour_str, sep, minute_str = part.strip().partition(":")
        if not sep or not hour_str.isdigit() or not minute_str.isdigit():
            raise ValueError(f"bad CRON_SLOTS entry: {part!r}")
        hour, minute = int(hour_str), int(minute_str)
        if hour > 23 or minute > 59:
            raise ValueError(f"bad CRON_SLOTS entry: {part!r}")
        slots.append((hour, minute))
    return slots


def next_slot(now_utc: datetime, slots: list) -> datetime:
    """Earliest slot strictly after `now_utc`, wrapping past midnight."""
    day = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    return min(
        candidate
        for offset in (0, 1)
        for hour, minute in slots
        if (candidate := day + timedelta(days=offset, hours=hour, minutes=minute)) > now_utc
    )


def alert_timeout(label: str, error: subprocess.TimeoutExpired) -> None:
    """Telegram alert; the killed child cannot send its own."""
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from utils.handle_telegram import notify_developer  # pylint: disable=import-outside-toplevel

        notify_developer(
            body=f"cron_clock slot={label}: {error.cmd[-1]} killed after {error.timeout}s",
            subject="Cronjob Report",
        )
    except Exception as alert_error:  # pylint: disable=broad-except
        print(f"cron_clock slot={label} alert failed: {alert_error!r}", flush=True)


def run_slot(label: str) -> None:
    needs_work, code = False, None
    try:
        probe = subprocess.run(
            [sys.executable, "scripts/cron_probe.py"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False,
            timeout=PROBE_TIMEOUT_S,
        )
        print(probe.stdout, end="", flush=True)
        print(probe.stderr, end="", file=sys.stderr, flush=True)
        code = probe.returncode
        needs_work = code == 0 and "needs_work=true" in probe.stdout
        if needs_work:
            code = subprocess.run(
                [sys.executable, "cronjob.py"], cwd=REPO_ROOT, check=False,
                timeout=CRONJOB_TIMEOUT_S,
            ).returncode
    except subprocess.TimeoutExpired as error:
        code = "timeout"
        print(f"cron_clock slot={label} timeout: {error.cmd[-1]} after {error.timeout}s", flush=True)
        alert_timeout(label, error)
    except Exception as error:  # pylint: disable=broad-except
        print(f"cron_clock slot={label} error: {error!r}", flush=True)
    print(
        f"cron_clock slot={label} needs_work={str(needs_work).lower()} exit={code}",
        flush=True,
    )


def main() -> None:
    slots = parse_slots(os.getenv("CRON_SLOTS") or DEFAULT_SLOTS)
    print(
        "cron_clock slots (UTC): " + ",".join(f"{h:02d}:{m:02d}" for h, m in slots),
        flush=True,
    )
    while True:
        target = next_slot(datetime.now(timezone.utc), slots)
        # One long sleep: a dyno restart mid-sleep skips that slot; the next probe recovers it.
        time.sleep(max(0.0, (target - datetime.now(timezone.utc)).total_seconds()))
        run_slot(target.strftime("%H:%M"))


if __name__ == "__main__":
    main()
