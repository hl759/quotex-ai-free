from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, List, Optional

from alpha_hive.storage.storage_paths import DATA_DIR, ensure_parent

log = logging.getLogger(__name__)

try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool
    _HAS_PSYCOPG2 = True
except Exception:
    psycopg2 = None  # type: ignore[assignment]
    _HAS_PSYCOPG2 = False

SQLITE_DB_PATH = os.getenv("ALPHA_HIVE_DB_PATH", str(DATA_DIR / "alpha_hive_state.db"))
DATABASE_URL = (
    os.getenv("ALPHA_HIVE_DATABASE_URL", "").strip()
    or os.getenv("DATABASE_URL", "").strip()
)
# Segundo banco (failover automático). Use DATABASE_URL_2 ou ALPHA_HIVE_DATABASE_URL_2.
DATABASE_URL_2 = (
    os.getenv("ALPHA_HIVE_DATABASE_URL_2", "").strip()
    or os.getenv("DATABASE_URL_2", "").strip()
)
ensure_parent(SQLITE_DB_PATH)

# Pool conservador: máximo 4 conexões simultâneas.
# Aiven free suporta 25 — ficamos bem dentro do limite mesmo com scan paralelo.
_PG_POOL_MIN = 1
_PG_POOL_MAX = 4

_SINGLETON_LOCK = threading.Lock()
_SINGLETON_STORE: Optional["StateStore"] = None


def _is_postgres_url(url: str) -> bool:
    return url.startswith(("postgres://", "postgresql://"))


def _ensure_sslmode(url: str) -> str:
    """Garante sslmode=require para Aiven (e qualquer PG remoto sem SSL explícito)."""
    if "sslmode=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}sslmode=require"


class StateStore:
    """
    Armazenamento de estado com suporte a PostgreSQL (via pool de conexões)
    e fallback automático: DB-primário → DB-secundário → SQLite.

    Configuração:
        DATABASE_URL            → PostgreSQL primário (Aiven #1)
        DATABASE_URL_2          → PostgreSQL secundário / failover (Aiven #2)
        ALPHA_HIVE_DATABASE_URL → alias para DATABASE_URL
        ALPHA_HIVE_DATABASE_URL_2 → alias para DATABASE_URL_2

    Se o primário falhar na inicialização ou em operação, chaveia para o
    secundário automaticamente. Se ambos falharem, usa SQLite local.
    """

    def __init__(
        self,
        db_path: str = SQLITE_DB_PATH,
        database_url: str = DATABASE_URL,
        database_url_2: str = DATABASE_URL_2,
    ):
        self.db_path = db_path
        self.database_url = database_url
        self.database_url_2 = database_url_2
        self._write_lock = threading.Lock()
        self._pool: Any = None
        self._pool_2: Any = None  # pool do banco secundário
        self.fallback_reason: Optional[str] = None
        self.last_error: Optional[str] = None

        wants_pg = _is_postgres_url(database_url) and _HAS_PSYCOPG2
        self.use_postgres = False

        if wants_pg:
            self._init_pool(database_url)

        # Inicializa pool secundário se URL_2 estiver configurada
        if _is_postgres_url(database_url_2) and _HAS_PSYCOPG2:
            self._init_pool_2(database_url_2)

        self.backend_name = "postgres" if self.use_postgres else "sqlite"
        self.backend_target = database_url if self.use_postgres else db_path

        self._init_schema()

    # ── Pool / conexão ────────────────────────────────────────────────────

    def _init_pool(self, url: str) -> None:
        safe_url = _ensure_sslmode(url)
        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                _PG_POOL_MIN,
                _PG_POOL_MAX,
                dsn=safe_url,
                connect_timeout=8,
                # TCP keepalive — mantém conexões vivas no Aiven (que fecha após ~5 min ociosas)
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5,
            )
            conn = self._pool.getconn()
            self._pool.putconn(conn)
            self.use_postgres = True
            log.info("StateStore: PostgreSQL primário conectado (%d–%d conns)", _PG_POOL_MIN, _PG_POOL_MAX)
        except Exception as exc:
            self._pool = None
            self.use_postgres = False
            self.fallback_reason = "pg_primary_failed"
            self.last_error = repr(exc)
            log.warning("StateStore: falha no PostgreSQL primário (%s)", exc)

    def _init_pool_2(self, url: str) -> None:
        safe_url = _ensure_sslmode(url)
        try:
            self._pool_2 = psycopg2.pool.ThreadedConnectionPool(
                _PG_POOL_MIN,
                _PG_POOL_MAX,
                dsn=safe_url,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5,
                connect_timeout=8,
            )
            conn = self._pool_2.getconn()
            self._pool_2.putconn(conn)
            # Se o primário falhou, o secundário assume como ativo
            if not self.use_postgres:
                self._pool, self._pool_2 = self._pool_2, None
                self.use_postgres = True
                self.fallback_reason = "pg_using_secondary"
                log.info("StateStore: PostgreSQL secundário assumiu como primário")
            else:
                log.info("StateStore: PostgreSQL secundário conectado (failover em standby)")
        except Exception as exc:
            self._pool_2 = None
            log.warning("StateStore: falha no PostgreSQL secundário (%s)", exc)

    def _validate_conn(self, conn) -> bool:
        """Verifica se a conexão ainda está viva com SELECT 1."""
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            return False

    def _acquire_pg_conn(self):
        """Adquire e valida conexão do pool. Descarta conexões mortas (SSL stale)."""
        for attempt in range(2):
            conn = None
            try:
                conn = self._pool.getconn()
                conn.autocommit = True
                if self._validate_conn(conn):
                    return conn
                # Conexão morta — descarta e tenta de novo
                log.warning("StateStore: conexão obsoleta descartada (tentativa %d)", attempt + 1)
                try:
                    self._pool.putconn(conn, close=True)
                except Exception:
                    pass
                conn = None
                # Continua para a próxima iteração do loop
            except psycopg2.pool.PoolError:
                return None  # pool esgotado → SQLite
            except Exception as exc:
                self.last_error = repr(exc)
                if conn is not None:
                    try:
                        self._pool.putconn(conn, close=True)
                    except Exception:
                        pass
                if attempt == 1:
                    # Segunda falha: tenta failover para banco secundário
                    if self._failover_to_secondary():
                        try:
                            c = self._pool.getconn()
                            c.autocommit = True
                            return c
                        except Exception as exc2:
                            self.last_error = repr(exc2)
                    return None
                # attempt == 0: continua para tentativa 1
        return None

    def _is_pg_conn(self, conn) -> bool:
        """Retorna True se a conexão é realmente PostgreSQL (não SQLite fallback)."""
        return not isinstance(conn, sqlite3.Connection)

    def _run_with_retry(self, fn):
        """Executa fn(conn, is_pg) com retry automático em OperationalError SSL."""
        for attempt in range(2):
            try:
                with self._connect() as conn:
                    return fn(conn, self._is_pg_conn(conn))
            except Exception as exc:
                if (
                    attempt == 0
                    and _HAS_PSYCOPG2
                    and isinstance(exc, psycopg2.OperationalError)
                ):
                    log.warning("StateStore: SSL error mid-query, retentando (%s)", exc)
                    continue
                raise
        return None  # nunca alcançado normalmente

    @contextmanager
    def _connect(self) -> Generator:
        if self.use_postgres and self._pool is not None:
            conn = self._acquire_pg_conn()
            if conn is not None:
                try:
                    yield conn
                finally:
                    try:
                        self._pool.putconn(conn)
                    except Exception:
                        pass
                return
            log.warning("StateStore: PostgreSQL indisponível nesta operação, usando SQLite")

        with self._sqlite_connect() as conn:
            yield conn

    @contextmanager
    def _sqlite_connect(self) -> Generator:
        conn = sqlite3.connect(
            self.db_path, timeout=15, isolation_level=None, check_same_thread=False
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
        finally:
            conn.close()

    # ── Schema ────────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        def _create(conn, is_pg):
            if is_pg:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS kv (
                            key         TEXT PRIMARY KEY,
                            value_json  JSONB NOT NULL,
                            updated_at  TEXT  NOT NULL
                        )
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS collection_items (
                            collection_name TEXT NOT NULL,
                            uid             TEXT NOT NULL,
                            created_at      TEXT NOT NULL,
                            updated_at      TEXT NOT NULL,
                            payload_json    JSONB NOT NULL,
                            PRIMARY KEY (collection_name, uid)
                        )
                    """)
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_ci_collection_updated
                        ON collection_items (collection_name, updated_at DESC)
                    """)
            else:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS kv (
                        key         TEXT PRIMARY KEY,
                        value_json  TEXT NOT NULL,
                        updated_at  TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS collection_items (
                        collection_name TEXT NOT NULL,
                        uid             TEXT NOT NULL,
                        created_at      TEXT NOT NULL,
                        updated_at      TEXT NOT NULL,
                        payload_json    TEXT NOT NULL,
                        PRIMARY KEY (collection_name, uid)
                    )
                """)
        try:
            self._run_with_retry(_create)
        except Exception as exc:
            log.warning("StateStore: falha ao criar schema (%s)", exc)

    # ── Serialização ──────────────────────────────────────────────────────

    def _dump(self, value: Any, is_pg: bool = True) -> Any:
        if is_pg:
            return psycopg2.extras.Json(value)
        return json.dumps(value, ensure_ascii=False)

    def _load(self, raw: Any, is_pg: bool = True) -> Any:
        if raw is None:
            return None
        if is_pg:
            return raw  # psycopg2 já desserializa JSONB automaticamente
        try:
            return json.loads(raw)
        except Exception:
            return None

    # ── KV Store ─────────────────────────────────────────────────────────

    def get_json(self, key: str, default: Any = None) -> Any:
        def _q(conn, is_pg):
            if is_pg:
                with conn.cursor() as cur:
                    cur.execute("SELECT value_json FROM kv WHERE key=%s", (key,))
                    row = cur.fetchone()
            else:
                row = conn.execute("SELECT value_json FROM kv WHERE key=?", (key,)).fetchone()
            value = self._load(row[0] if row else None, is_pg)
            return default if value is None else value
        try:
            return self._run_with_retry(_q)
        except Exception:
            return default

    def set_json(self, key: str, value: Any) -> None:
        now = datetime.now(timezone.utc).isoformat()
        def _q(conn, is_pg):
            payload = self._dump(value, is_pg)
            if is_pg:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO kv (key, value_json, updated_at)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (key) DO UPDATE
                            SET value_json = EXCLUDED.value_json,
                                updated_at = EXCLUDED.updated_at
                        """,
                        (key, payload, now),
                    )
            else:
                conn.execute(
                    """
                    INSERT INTO kv (key, value_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT (key) DO UPDATE
                        SET value_json = excluded.value_json,
                            updated_at = excluded.updated_at
                    """,
                    (key, payload, now),
                )
        with self._write_lock:
            try:
                self._run_with_retry(_q)
            except Exception as exc:
                log.warning("StateStore: set_json falhou (%s)", exc)

    # ── Coleções ──────────────────────────────────────────────────────────

    def append_unique_item(
        self,
        collection_name: str,
        uid: str,
        payload: Dict[str, Any],
        created_at: Optional[str] = None,
    ) -> bool:
        ts = created_at or datetime.now(timezone.utc).isoformat()
        def _q(conn, is_pg):
            raw = self._dump(payload, is_pg)
            if is_pg:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO collection_items
                            (collection_name, uid, created_at, updated_at, payload_json)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (collection_name, uid) DO NOTHING
                        """,
                        (collection_name, uid, ts, ts, raw),
                    )
                    return (cur.rowcount or 0) > 0
            cur = conn.execute(
                """
                INSERT INTO collection_items
                    (collection_name, uid, created_at, updated_at, payload_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (collection_name, uid) DO NOTHING
                """,
                (collection_name, uid, ts, ts, raw),
            )
            return (cur.rowcount or 0) > 0
        with self._write_lock:
            try:
                return self._run_with_retry(_q) or False
            except Exception:
                return False

    def upsert_collection_item(
        self,
        collection_name: str,
        uid: str,
        payload: Dict[str, Any],
        created_at: Optional[str] = None,
    ) -> None:
        ts = created_at or datetime.now(timezone.utc).isoformat()
        def _q(conn, is_pg):
            raw = self._dump(payload, is_pg)
            if is_pg:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO collection_items
                            (collection_name, uid, created_at, updated_at, payload_json)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (collection_name, uid) DO UPDATE
                            SET payload_json = EXCLUDED.payload_json,
                                updated_at   = EXCLUDED.updated_at
                        """,
                        (collection_name, uid, ts, ts, raw),
                    )
            else:
                conn.execute(
                    """
                    INSERT INTO collection_items
                        (collection_name, uid, created_at, updated_at, payload_json)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (collection_name, uid) DO UPDATE
                        SET payload_json = excluded.payload_json,
                            updated_at   = excluded.updated_at
                    """,
                    (collection_name, uid, ts, ts, raw),
                )
        with self._write_lock:
            try:
                self._run_with_retry(_q)
            except Exception as exc:
                log.warning("StateStore: upsert_collection_item falhou (%s)", exc)

    def list_collection(
        self, collection_name: str, limit: int = 200
    ) -> List[Dict[str, Any]]:
        limit = max(1, int(limit))
        def _q(conn, is_pg):
            if is_pg:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT payload_json FROM collection_items
                        WHERE collection_name = %s
                        ORDER BY updated_at DESC
                        LIMIT %s
                        """,
                        (collection_name, limit),
                    )
                    rows = cur.fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT payload_json FROM collection_items
                    WHERE collection_name = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (collection_name, limit),
                ).fetchall()
            return [v for row in (rows or []) if (v := self._load(row[0], is_pg)) is not None]
        try:
            return self._run_with_retry(_q) or []
        except Exception:
            return []

    def get_collection_item(
        self, collection_name: str, uid: str, default: Any = None
    ) -> Any:
        def _q(conn, is_pg):
            if is_pg:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT payload_json FROM collection_items WHERE collection_name=%s AND uid=%s",
                        (collection_name, uid),
                    )
                    row = cur.fetchone()
            else:
                row = conn.execute(
                    "SELECT payload_json FROM collection_items WHERE collection_name=? AND uid=?",
                    (collection_name, uid),
                ).fetchone()
            value = self._load(row[0] if row else None, is_pg)
            return default if value is None else value
        try:
            return self._run_with_retry(_q)
        except Exception:
            return default

    # ── Pruning ───────────────────────────────────────────────────────────

    def prune_collection(
        self,
        collection_name: str,
        keep_latest: int = 4000,
        max_age_days: int = 90,
    ) -> int:
        keep_latest = max(100, int(keep_latest))
        cutoff = (datetime.utcnow() - timedelta(days=max_age_days)).isoformat()
        def _q(conn, is_pg):
            if is_pg:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM collection_items
                        WHERE collection_name = %s
                          AND (
                              created_at < %s
                              OR uid NOT IN (
                                  SELECT uid FROM collection_items
                                  WHERE collection_name = %s
                                  ORDER BY updated_at DESC
                                  LIMIT %s
                              )
                          )
                        """,
                        (collection_name, cutoff, collection_name, keep_latest),
                    )
                    return cur.rowcount or 0
            cur = conn.execute(
                """
                DELETE FROM collection_items
                WHERE collection_name = ?
                  AND (
                      created_at < ?
                      OR uid NOT IN (
                          SELECT uid FROM collection_items
                          WHERE collection_name = ?
                          ORDER BY updated_at DESC
                          LIMIT ?
                      )
                  )
                """,
                (collection_name, cutoff, collection_name, keep_latest),
            )
            return cur.rowcount or 0
        with self._write_lock:
            try:
                removed = self._run_with_retry(_q) or 0
            except Exception:
                removed = 0
        if removed:
            log.info("StateStore: pruning '%s' removeu %d registros", collection_name, removed)
        return int(removed)

    def prune_all(self) -> Dict[str, int]:
        """Prune automático em todas as coleções conhecidas. Chame 1x por dia."""
        limits = {
            "edge_trade_ledger_v2": (5000, 120),
            "trade_ledger":         (5000, 120),
            "collection_items":     (2000,  60),
        }
        result: Dict[str, int] = {}
        for name, (keep, days) in limits.items():
            removed = self.prune_collection(name, keep_latest=keep, max_age_days=days)
            if removed:
                result[name] = removed
        return result

    # ── Diagnóstico ───────────────────────────────────────────────────────

    def health(self) -> Dict[str, Any]:
        def _pool_info(p: Any) -> Optional[Dict]:
            if p is None:
                return None
            try:
                return {"min": _PG_POOL_MIN, "max": _PG_POOL_MAX, "closed": p.closed}
            except Exception:
                return None

        return {
            "backend": self.backend_name,
            "target": self.backend_target,
            "fallback_reason": self.fallback_reason,
            "last_error": self.last_error,
            "pool_primary": _pool_info(self._pool),
            "pool_secondary": _pool_info(self._pool_2),
            "has_failover": self._pool_2 is not None,
        }

    def close(self) -> None:
        for pool in (self._pool, self._pool_2):
            if pool is not None:
                try:
                    pool.closeall()
                except Exception:
                    pass


def get_state_store() -> StateStore:
    global _SINGLETON_STORE
    if _SINGLETON_STORE is None:
        with _SINGLETON_LOCK:
            if _SINGLETON_STORE is None:
                _SINGLETON_STORE = StateStore()
    return _SINGLETON_STORE
