"""Regression coverage for probe dependency imports."""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_PROBE_REQUIREMENTS = {"psycopg[binary]", "psycopg-pool"}


def test_probe_requirements_cover_provider_import_chain():
    requirements = {
        line.strip()
        for line in (ROOT / "requirements-probe.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert REQUIRED_PROBE_REQUIREMENTS <= requirements


def test_probe_imports_cleanly():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from services.cron_dates import needs_ingest; import scripts.cron_probe",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
