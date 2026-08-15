from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

import redis


@dataclass
class CacheItem:
    expires_at: datetime
    value: Any


class CacheProvider(Protocol):
    def get(self, key: str) -> Optional[Any]: ...

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None: ...


class TTLCache:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self._store: Dict[str, CacheItem] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            if datetime.utcnow() >= item.expires_at:
                self._store.pop(key, None)
                return None
            return item.value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = timedelta(seconds=ttl_seconds) if ttl_seconds else self.ttl
        with self._lock:
            self._store[key] = CacheItem(
                expires_at=datetime.utcnow() + ttl, value=value
            )


class RedisCache:
    def __init__(
        self,
        url: str,
        prefix: str = "",
        fallback: Optional[CacheProvider] = None,
    ) -> None:
        self.client = redis.from_url(url, decode_responses=True)
        self.prefix = prefix
        self.fallback = fallback

    def get(self, key: str) -> Optional[Any]:
        try:
            raw = self.client.get(f"{self.prefix}{key}")
        except redis.RedisError:
            if self.fallback is None:
                raise
            return self.fallback.get(key)
        if raw is None:
            return None
        return raw

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds or 3600
        try:
            self.client.setex(f"{self.prefix}{key}", ttl, value)
        except redis.RedisError:
            if self.fallback is None:
                raise
            self.fallback.set(key, value, ttl_seconds=ttl_seconds)


class SQLiteCache:
    """On-disk SQLite-backed cache with TTL eviction.

    Falls back transparently when Redis is unavailable, making the
    open-core package fully usable offline and in single-node deployments.
    """

    def __init__(
        self,
        path: str = ":memory:",
        ttl_seconds: int = 3600,
    ) -> None:
        self.path = path
        self.ttl = ttl_seconds
        self._lock = threading.Lock()
        self._memory_connection: sqlite3.Connection | None = None
        self._memory_fallback = TTLCache(ttl_seconds)
        self._read_only = False
        if path == ":memory:":
            self._memory_connection = sqlite3.connect(path, check_same_thread=False)
        else:
            expanded_path = Path(path).expanduser()
            expanded_path.parent.mkdir(parents=True, exist_ok=True)
            self.path = str(expanded_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_connection is not None:
            return self._memory_connection
        return sqlite3.connect(self.path)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at)"
            )
            conn.commit()

    def _now(self) -> float:
        return datetime.utcnow().timestamp()

    @staticmethod
    def _is_read_only_error(exc: sqlite3.OperationalError) -> bool:
        message = str(exc).lower()
        return "readonly" in message or "read-only" in message

    def _use_memory_fallback(self) -> None:
        self._read_only = True

    def get(self, key: str) -> Optional[Any]:
        if self._read_only:
            return self._memory_fallback.get(key)
        with self._lock:
            try:
                with self._connect() as conn:
                    cursor = conn.execute(
                        "SELECT value, expires_at FROM cache WHERE key = ?",
                        (key,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        return None
                    value, expires_at = row
                    if self._now() >= expires_at:
                        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                        conn.commit()
                        return None
                return value
            except sqlite3.OperationalError as exc:
                if not self._is_read_only_error(exc):
                    raise
                self._use_memory_fallback()
                return self._memory_fallback.get(key)

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        if self._read_only:
            self._memory_fallback.set(key, value, ttl_seconds=ttl_seconds)
            return
        ttl = ttl_seconds or self.ttl
        expires_at = self._now() + ttl
        raw = json.dumps(value) if not isinstance(value, str) else value
        with self._lock:
            try:
                with self._connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO cache(key, value, expires_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(key) DO UPDATE SET
                            value = excluded.value,
                            expires_at = excluded.expires_at
                        """,
                        (key, raw, expires_at),
                    )
                    conn.commit()
            except sqlite3.OperationalError as exc:
                if not self._is_read_only_error(exc):
                    raise
                self._use_memory_fallback()
                self._memory_fallback.set(key, value, ttl_seconds=ttl_seconds)

    def evict_expired(self) -> int:
        """Manually purge expired entries. Returns number of rows removed."""
        if self._read_only:
            return 0
        with self._lock:
            try:
                with self._connect() as conn:
                    cursor = conn.execute(
                        "DELETE FROM cache WHERE expires_at <= ?",
                        (self._now(),),
                    )
                    conn.commit()
                    return cursor.rowcount
            except sqlite3.OperationalError as exc:
                if not self._is_read_only_error(exc):
                    raise
                self._use_memory_fallback()
                return 0


def _default_sqlite_path() -> str:
    configured = os.getenv("OPASTRO_CACHE_PATH")
    if configured:
        return configured
    config_dir = os.getenv("OPASTRO_CONFIG_DIR")
    if config_dir:
        return os.path.join(config_dir, "cache.sqlite")
    return os.path.expanduser("~/.cache/opastro/cache.sqlite")


def cache_from_env(default_ttl: int) -> CacheProvider:
    url = os.getenv("REDIS_URL")
    prefix = os.getenv("REDIS_KEY_PREFIX", "")
    cache_path = _default_sqlite_path()
    sqlite_cache = SQLiteCache(path=cache_path, ttl_seconds=default_ttl)
    if url:
        return RedisCache(url, prefix=prefix, fallback=sqlite_cache)
    # Prefer SQLite over in-memory TTLCache for persistence across restarts.
    return sqlite_cache
