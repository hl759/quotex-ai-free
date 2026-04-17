from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from alpha_hive.storage.storage_paths import DATA_DIR, ensure_parent

try:
    import psycopg2
    import psycopg2.extras
except Exception:
    psycopg2 = None

SQLITE_DB_PATH = os.getenv("ALPHA_HIVE_DB_PATH", str(DATA_DIR / "alpha_hive_state.db"))
DATABASE_URL = (os.getenv("ALPHA_HIVE_DATABASE_URL", "").strip() or os.getenv("DATABASE_URL", "").strip())
ensure_parent(SQLITE_DB_PATH)

_SINGLETON_LOCK = threading.Lock()
_SINGLETON_STORE: Optional["StateStore"] = None


class StateStore:
    def __init__(self, db_path: str = SQLITE_DB_PATH, database_url: str = DATABASE_URL):
        self.db_path = db_path
        self.database_url = database_url
        self._lock = threading.Lock()
        self.requested_backend = "postgres" if database_url.startswith(("postgres://", "postgresql://")) else "sqlite"
        self.use_postgres = bool(self.requested_backend == "postgres" and psycopg2 is not None)
        self.backend_name = "postgres" if self.use_postgres else "sqlite"
        self.backend_target = self.database_url if self.use_postgres else self.db_path
        self.fallback_reason: Optional[str] = None
        self.last_error: Optional[str] = None
        self._init_db()

    @contextmanager
    def _connect(self):
        if self.use_postgres:
            try:
                conn = psycopg2.connect(self.database_url, connect_timeout=5)
                conn.autocommit = True
                try:
                    yield conn
                finally:
                    conn.close()
                return
            except Exception as exc:
                self.use_postgres = False
                self.backend_name = "sqlite"
                self.backend_target = self.db_path
                self.fallback_reason = "postgres_connect_failed"
                self.last_error = repr(exc)

        conn = sqlite3.connect(self.db_path, timeout=15, isolation_level=None, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            if self.use_postgres:
                with conn.cursor() as cur:
                    cur.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value_json JSONB NOT NULL, updated_at TEXT NOT NULL)")
                    cur.execute(
                        "CREATE TABLE IF NOT EXISTS collection_items (collection_name TEXT NOT NULL, uid TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, payload_json JSONB NOT NULL, PRIMARY KEY(collection_name, uid))"
                    )
            else:
                conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL)")
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS collection_items (collection_name TEXT NOT NULL, uid TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(collection_name, uid))"
                )

    def _dump(self, value: Any) -> Any:
        if self.use_postgres:
            return psycopg2.extras.Json(value)
        return json.dumps(value, ensure_ascii=False)

    def _load_row(self, row, idx: int = 0):
        if not row:
            return None
        value = row[idx]
        if value is None:
            return None
        if self.use_postgres:
            return value
        try:
            return json.loads(value)
        except Exception:
            return None

    def get_json(self, key: str, default: Any = None) -> Any:
        with self._connect() as conn:
            if self.use_postgres:
                with conn.cursor() as cur:
                    cur.execute("SELECT value_json FROM kv WHERE key=%s", (key,))
                    row = cur.fetchone()
            else:
                row = conn.execute("SELECT value_json FROM kv WHERE key=?", (key,)).fetchone()
        value = self._load_row(row)
        return default if value is None else value

    def set_json(self, key: str, value: Any) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = self._dump(value)
        with self._lock:
            with self._connect() as conn:
                if self.use_postgres:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO kv(key, value_json, updated_at) VALUES(%s,%s,%s) ON CONFLICT(key) DO UPDATE SET value_json=EXCLUDED.value_json, updated_at=EXCLUDED.updated_at",
                            (key, payload, now),
                        )
                else:
                    conn.execute(
                        "INSERT INTO kv(key, value_json, updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
                        (key, payload, now),
                    )

    def append_unique_item(self, collection_name: str, uid: str, payload: Dict[str, Any], created_at: Optional[str] = None) -> bool:
        ts = created_at or datetime.now(timezone.utc).isoformat()
        raw = self._dump(payload)
        with self._lock:
            with self._connect() as conn:
                if self.use_postgres:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO collection_items(collection_name, uid, created_at, updated_at, payload_json) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(collection_name, uid) DO NOTHING",
                            (collection_name, uid, ts, ts, raw),
                        )
                        return (cur.rowcount or 0) > 0
                cur = conn.execute(
                    "INSERT INTO collection_items(collection_name, uid, created_at, updated_at, payload_json) VALUES(?,?,?,?,?) ON CONFLICT(collection_name, uid) DO NOTHING",
                    (collection_name, uid, ts, ts, raw),
                )
                return (cur.rowcount or 0) > 0

    def upsert_collection_item(self, collection_name: str, uid: str, payload: Dict[str, Any], created_at: Optional[str] = None) -> None:
        ts = created_at or datetime.now(timezone.utc).isoformat()
        raw = self._dump(payload)
        with self._lock:
            with self._connect() as conn:
                if self.use_postgres:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO collection_items(collection_name, uid, created_at, updated_at, payload_json) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(collection_name, uid) DO UPDATE SET payload_json=EXCLUDED.payload_json, updated_at=EXCLUDED.updated_at",
                            (collection_name, uid, ts, ts, raw),
                        )
                else:
                    conn.execute(
                        "INSERT INTO collection_items(collection_name, uid, created_at, updated_at, payload_json) VALUES(?,?,?,?,?) ON CONFLICT(collection_name, uid) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at",
                        (collection_name, uid, ts, ts, raw),
                    )

    def list_collection(self, collection_name: str, limit: int = 200) -> List[Dict[str, Any]]:
        limit = max(1, int(limit))
        with self._connect() as conn:
            if self.use_postgres:
                with conn.cursor() as cur:
                    cur.execute("SELECT payload_json FROM collection_items WHERE collection_name=%s ORDER BY updated_at DESC LIMIT %s", (collection_name, limit))
                    rows = cur.fetchall()
            else:
                rows = conn.execute(
                    "SELECT payload_json FROM collection_items WHERE collection_name=? ORDER BY updated_at DESC LIMIT ?",
                    (collection_name, limit),
                ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows or []:
            value = self._load_row(row)
            if value is not None:
                out.append(value)
        return out

    def get_collection_item(self, collection_name: str, uid: str, default: Any = None) -> Any:
        with self._connect() as conn:
            if self.use_postgres:
                with conn.cursor() as cur:
                    cur.execute("SELECT payload_json FROM collection_items WHERE collection_name=%s AND uid=%s", (collection_name, uid))
                    row = cur.fetchone()
            else:
                row = conn.execute(
                    "SELECT payload_json FROM collection_items WHERE collection_name=? AND uid=?",
                    (collection_name, uid),
                ).fetchone()
        value = self._load_row(row)
        return default if value is None else value

    def health(self) -> Dict[str, Any]:
        return {
            "backend": self.backend_name,
            "target": self.backend_target,
            "fallback_reason": self.fallback_reason,
            "last_error": self.last_error,
        }

    def prune_collection(self, collection_name: str, keep_latest: int = 4000, max_age_days: int = 90) -> int:
        keep_latest = max(100, int(keep_latest))
        cutoff = (datetime.utcnow() - timedelta(days=max_age_days)).isoformat()
        removed = 0
        with self._lock:
            with self._connect() as conn:
                if self.use_postgres:
                    with conn.cursor() as cur:
                        cur.execute(
                            '''
                            DELETE FROM collection_items
                            WHERE collection_name=%s
                              AND (created_at < %s OR uid NOT IN (
                                    SELECT uid FROM collection_items
                                    WHERE collection_name=%s
                                    ORDER BY updated_at DESC LIMIT %s
                              ))
                            ''',
                            (collection_name, cutoff, collection_name, keep_latest),
                        )
                        removed = cur.rowcount or 0
                else:
                    cur = conn.execute(
                        '''
                        DELETE FROM collection_items
                        WHERE collection_name=?
                          AND (created_at < ? OR uid NOT IN (
                                SELECT uid FROM collection_items
                                WHERE collection_name=?
                                ORDER BY updated_at DESC LIMIT ?
                          ))
                        ''',
                        (collection_name, cutoff, collection_name, keep_latest),
                    )
                    removed = cur.rowcount or 0
        return int(removed)


def get_state_store() -> StateStore:
    global _SINGLETON_STORE
    if _SINGLETON_STORE is None:
        with _SINGLETON_LOCK:
            if _SINGLETON_STORE is None:
                _SINGLETON_STORE = StateStore()
    return _SINGLETON_STORE
