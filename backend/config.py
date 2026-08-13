"""Central environment loader.

Every backend module reads configuration from the project-root `.env` file.
Importing this module loads the `.env` into the process environment once, and
`load_env()` can be called explicitly for an idempotent reload.
"""

import os
from pathlib import Path


def load_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()
