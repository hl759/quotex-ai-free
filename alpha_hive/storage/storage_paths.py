from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(os.getenv("ALPHA_HIVE_ROOT_DIR", os.getcwd()))
DATA_DIR = Path(os.getenv("ALPHA_HIVE_DATA_DIR", ROOT_DIR / "data"))
STATE_DIR = Path(os.getenv("ALPHA_HIVE_STATE_DIR", DATA_DIR / "state"))

for path in (DATA_DIR, STATE_DIR):
    path.mkdir(parents=True, exist_ok=True)

def ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
