"""Deploy revision and application version metadata."""

import os
import subprocess
from functools import lru_cache

APP_VERSION = "1.5.0"


@lru_cache(maxsize=1)
def get_deploy_revision() -> str:
    """Return full 40-char deploy commit SHA from env or git, else unknown."""
    for env_var in ("HEROKU_SLUG_COMMIT", "SOURCE_VERSION"):
        value = os.getenv(env_var)
        if value:
            return value.strip()

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"
