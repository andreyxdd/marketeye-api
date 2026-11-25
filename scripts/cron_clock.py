"""Heroku clock dyno: run probe -> cronjob at fixed UTC slots, forever."""

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

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


def run_slot(label: str) -> None:
    needs_work, code = False, None
    try:
        probe = subprocess.run(
            [sys.executable, "scripts/cron_probe.py"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False,
        )
        print(probe.stdout, end="", flush=True)
        print(probe.stderr, end="", file=sys.stderr, flush=True)
        code = probe.returncode
        needs_work = code == 0 and "needs_work=true" in probe.stdout
        if needs_work:
            code = subprocess.run(
                [sys.executable, "cronjob.py"], cwd=REPO_ROOT, check=False
            ).returncode
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
