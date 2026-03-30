import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

from json_safe import to_jsonable
from storage_paths import DATA_DIR, ensure_parent

try:
    import psycopg2
    import psycopg2.extras
except Exception:  # pragma: no cover - optional runtime dependency
    psycopg2 = None

SQLITE_DB_PATH = os.getenv("ALPHA_HIVE_DB_PATH", os.path.join(DATA_DIR, "alpha_hive_state.db"))
ensure_parent(SQLITE_DB_PATH)

DATABASE_URL = (
    os.getenv("ALPHA_HIVE_DATABASE_URL", "").strip()
    or os.getenv("DATABASE_URL", "").strip()
)
USE_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith(("postgres://", "postgresql://")) and psycopg2 is not None)


class StateStore:
    def __init__(self, db_path=SQLITE_DB_PATH, database_url=DATABASE_URL):
        self.database_url = database_url.strip() if database_url else ""
        self.use_postgres = bool(self.database_url and self.database_url.startswith(("postgres://", "postgresql://")) and psycopg2 is not None)
        self.db_path = db_path
        self.backend_name = "postgres" if self.use_postgres else "sqlite"
        self.backend_target = self.database_url if self.use_postgres else self.db_path
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _connect(self):
        if self.use_postgres:
            conn = psycopg2.connect(self.database_url)
            conn.autocommit = True
            try:
                yield conn
            finally:
                conn.close()
            return

        conn = sqlite3.connect(self.db_path, timeout=15, isolation_level=None, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=15000")
        try:
            yield conn
        finally:
            conn.close()

    def _json_param(self, payload):
        text = json.dumps(to_jsonable(payload), ensure_ascii=False)
        if self.use_postgres:
            return psycopg2.extras.Json(json.loads(text))
        return text

    def _json_row_value(self, row, index=0):
        if not row:
            return None
        value = row[index]
        if value is None:
            return None
        if self.use_postgres:
            return value
        try:
            return json.loads(value)
        except Exception:
            return None

    def _init_db(self):
        with self._connect() as conn:
            if self.use_postgres:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS kv (
                            key TEXT PRIMARY KEY,
                            value_json JSONB NOT NULL,
                            updated_at TEXT NOT NULL
                        )
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS scans (
                            id BIGSERIAL PRIMARY KEY,
                            created_at TEXT NOT NULL,
                            scan_count INTEGER NOT NULL,
                            signal_count INTEGER NOT NULL,
                            decision TEXT,
                            asset TEXT,
                            snapshot_json JSONB NOT NULL
                        )
                        """
                    )
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_scans_scan_count ON scans(scan_count)")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_scans_created_at ON scans(created_at)")
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS collection_items (
                            collection_name TEXT NOT NULL,
                            uid TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            payload_json JSONB NOT NULL,
                            PRIMARY KEY (collection_name, uid)
                        )
                        """
                    )
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_collection_items_created ON collection_items(collection_name, created_at DESC)")
            else:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS kv (
                        key TEXT PRIMARY KEY,
                        value_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        scan_count INTEGER NOT NULL,
                        signal_count INTEGER NOT NULL,
                        decision TEXT,
                        asset TEXT,
                        snapshot_json TEXT NOT NULL
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scans_scan_count ON scans(scan_count)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scans_created_at ON scans(created_at)")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS collection_items (
                        collection_name TEXT NOT NULL,
                        uid TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        PRIMARY KEY (collection_name, uid)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_collection_items_created ON collection_items(collection_name, created_at DESC)")

    def get_json(self, key, default=None):
        with self._connect() as conn:
            if self.use_postgres:
                with conn.cursor() as cur:
                    cur.execute("SELECT value_json FROM kv WHERE key=%s", (str(key),))
                    row = cur.fetchone()
            else:
                row = conn.execute("SELECT value_json FROM kv WHERE key=?", (str(key),)).fetchone()
        value = self._json_row_value(row)
        return default if value is None else value

    def set_json(self, key, value):
        now = datetime.utcnow().isoformat()
        payload = self._json_param(value)
        with self._lock:
            with self._connect() as conn:
                if self.use_postgres:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO kv(key, value_json, updated_at)
                            VALUES(%s,%s,%s)
                            ON CONFLICT(key) DO UPDATE SET value_json=EXCLUDED.value_json, updated_at=EXCLUDED.updated_at
                            """,
                            (str(key), payload, now),
                        )
                else:
                    conn.execute(
                        "INSERT INTO kv(key, value_json, updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
                        (str(key), payload, now),
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
        payload = self._json_param(data)
        with self._lock:
            with self._connect() as conn:
                if self.use_postgres:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO scans(created_at, scan_count, signal_count, decision, asset, snapshot_json) VALUES(%s,%s,%s,%s,%s,%s)",
                            (created_at, int(scan_count), int(signal_count), decision, asset, payload),
                        )
                else:
                    conn.execute(
                        "INSERT INTO scans(created_at, scan_count, signal_count, decision, asset, snapshot_json) VALUES(?,?,?,?,?,?)",
                        (created_at, int(scan_count), int(signal_count), decision, asset, payload),
                    )
        self.set_int("scan_count", scan_count)
        self.set_json("last_snapshot", data)
        self.set_json("last_scan_at", created_at)

    def last_snapshot(self):
        snapshot = self.get_json("last_snapshot", None)
        if snapshot:
            return snapshot
        with self._connect() as conn:
            if self.use_postgres:
                with conn.cursor() as cur:
                    cur.execute("SELECT snapshot_json FROM scans ORDER BY id DESC LIMIT 1")
                    row = cur.fetchone()
            else:
                row = conn.execute("SELECT snapshot_json FROM scans ORDER BY id DESC LIMIT 1").fetchone()
        return self._json_row_value(row)

    def max_scan_count(self):
        with self._connect() as conn:
            if self.use_postgres:
                with conn.cursor() as cur:
                    cur.execute("SELECT MAX(scan_count) FROM scans")
                    row = cur.fetchone()
            else:
                row = conn.execute("SELECT MAX(scan_count) FROM scans").fetchone()
        try:
            return int((row or [0])[0] or 0)
        except Exception:
            return 0

    def get_collection_item(self, collection_name, uid, default=None):
        with self._connect() as conn:
            if self.use_postgres:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT payload_json FROM collection_items WHERE collection_name=%s AND uid=%s",
                        (str(collection_name), str(uid)),
                    )
                    row = cur.fetchone()
            else:
                row = conn.execute(
                    "SELECT payload_json FROM collection_items WHERE collection_name=? AND uid=?",
                    (str(collection_name), str(uid)),
                ).fetchone()
        value = self._json_row_value(row)
        return default if value is None else value

    def set_collection_item(self, collection_name, uid, payload, created_at=None):
        now = datetime.utcnow().isoformat()
        created_at = created_at or now
        payload_json = self._json_param(payload)
        with self._lock:
            with self._connect() as conn:
                if self.use_postgres:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO collection_items(collection_name, uid, created_at, updated_at, payload_json)
                            VALUES(%s,%s,%s,%s,%s)
                            ON CONFLICT(collection_name, uid)
                            DO UPDATE SET payload_json=EXCLUDED.payload_json, updated_at=EXCLUDED.updated_at
                            """,
                            (str(collection_name), str(uid), created_at, now, payload_json),
                        )
                else:
                    conn.execute(
                        """
                        INSERT INTO collection_items(collection_name, uid, created_at, updated_at, payload_json)
                        VALUES(?,?,?,?,?)
                        ON CONFLICT(collection_name, uid)
                        DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at
                        """,
                        (str(collection_name), str(uid), created_at, now, payload_json),
                    )

    def append_unique_item(self, collection_name, uid, payload, created_at=None):
        existing = self.get_collection_item(collection_name, uid, default=None)
        if existing is not None:
            return False
        self.set_collection_item(collection_name, uid, payload, created_at=created_at)
        return True

    def list_collection(self, collection_name, limit=None):
        limit_value = max(1, int(limit)) if limit else None
        with self._connect() as conn:
            if self.use_postgres:
                with conn.cursor() as cur:
                    if limit_value:
                        cur.execute(
                            "SELECT payload_json FROM collection_items WHERE collection_name=%s ORDER BY created_at DESC LIMIT %s",
                            (str(collection_name), limit_value),
                        )
                    else:
                        cur.execute(
                            "SELECT payload_json FROM collection_items WHERE collection_name=%s ORDER BY created_at DESC",
                            (str(collection_name),),
                        )
                    rows = cur.fetchall()
            else:
                if limit_value:
                    rows = conn.execute(
                        "SELECT payload_json FROM collection_items WHERE collection_name=? ORDER BY created_at DESC LIMIT ?",
                        (str(collection_name), limit_value),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT payload_json FROM collection_items WHERE collection_name=? ORDER BY created_at DESC",
                        (str(collection_name),),
                    ).fetchall()
        output = []
        for row in rows or []:
            value = self._json_row_value(row)
            if value is not None:
                output.append(value)
        return output


_STATE_STORE_SINGLETON = None


def get_state_store():
    global _STATE_STORE_SINGLETON
    if _STATE_STORE_SINGLETON is None:
        _STATE_STORE_SINGLETON = StateStore()
    return _STATE_STORE_SINGLETON
