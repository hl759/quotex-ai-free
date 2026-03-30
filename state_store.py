import json
import os
import sqlite3
import threading
from datetime import datetime

from json_safe import to_jsonable
from storage_paths import DATA_DIR, ensure_parent

DB_PATH = os.getenv("ALPHA_HIVE_DB_PATH", os.path.join(DATA_DIR, "alpha_hive_state.db"))
ensure_parent(DB_PATH)

class StateStore:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=15, isolation_level=None, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kv (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    scan_count INTEGER NOT NULL,
                    signal_count INTEGER NOT NULL,
                    decision TEXT,
                    asset TEXT,
                    snapshot_json TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scans_scan_count ON scans(scan_count)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scans_created_at ON scans(created_at)")

    def get_json(self, key, default=None):
        with self._connect() as conn:
            row = conn.execute("SELECT value_json FROM kv WHERE key=?", (str(key),)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row[0])
        except Exception:
            return default

    def set_json(self, key, value):
        payload = json.dumps(to_jsonable(value), ensure_ascii=False)
        now = datetime.utcnow().isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO kv(key, value_json, updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
                    (str(key), payload, now)
                )

    def get_int(self, key, default=0):
        value = self.get_json(key, default)
        try:
            return int(value)
        except Exception:
            return int(default)

    def set_int(self, key, value):
        try:
            value = int(value)
        except Exception:
            return
        self.set_json(key, value)

    def append_scan(self, snapshot, scan_count):
        data = to_jsonable(snapshot or {})
        created_at = datetime.utcnow().isoformat()
        signal_count = len(data.get("signals") or []) if isinstance(data, dict) else 0
        current_decision = data.get("current_decision") if isinstance(data, dict) else {}
        decision = None
        asset = None
        if isinstance(current_decision, dict):
            decision = current_decision.get("decision")
            asset = current_decision.get("asset")
        payload = json.dumps(data, ensure_ascii=False)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO scans(created_at, scan_count, signal_count, decision, asset, snapshot_json) VALUES(?,?,?,?,?,?)",
                    (created_at, int(scan_count), int(signal_count), decision, asset, payload)
                )
        self.set_int("scan_count", scan_count)
        self.set_json("last_snapshot", data)
        self.set_json("last_scan_at", created_at)

    def last_snapshot(self):
        snapshot = self.get_json("last_snapshot", None)
        if snapshot:
            return snapshot
        with self._connect() as conn:
            row = conn.execute("SELECT snapshot_json FROM scans ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

    def max_scan_count(self):
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(scan_count) FROM scans").fetchone()
        try:
            return int(row[0] or 0)
        except Exception:
            return 0
