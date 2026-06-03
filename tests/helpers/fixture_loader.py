"""Load JSON fixture maps from disk."""

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def load_json(relative_path: str):
    path = FIXTURES_DIR / relative_path
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)
