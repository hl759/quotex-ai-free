import os
import shutil

PROJECT_ROOT = os.getcwd()
DATA_DIR = os.getenv("ALPHA_HIVE_DATA_DIR") or os.getenv("STATE_DIR") or os.path.join(PROJECT_ROOT, "alpha_hive_data")
STATE_DIR = os.getenv("STATE_DIR") or DATA_DIR

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(STATE_DIR, exist_ok=True)

def ensure_parent(path: str):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

def migrate_file(dest: str, candidates):
    ensure_parent(dest)
    if os.path.exists(dest):
        return None
    for src in candidates:
        try:
            if not src or not os.path.exists(src):
                continue
            if os.path.realpath(src) == os.path.realpath(dest):
                continue
            shutil.copy2(src, dest)
            return src
        except Exception:
            continue
    return None
