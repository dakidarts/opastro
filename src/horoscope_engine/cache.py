from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
import sqlite3
import threading
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
    def __init__(self, url: str, prefix: str = "") -> None:
        self.client = redis.from_url(url, decode_responses=True)
        self.prefix = prefix

    def get(self, key: str) -> Optional[Any]:
        raw = self.client.get(f"{self.prefix}{key}")
        if raw is None:
            return None
        return raw

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds or 3600
        self.client.setex(f"{self.prefix}{key}", ttl, value)


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
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.path) as conn:
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

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            with sqlite3.connect(self.path) as conn:
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

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds or self.ttl
        expires_at = self._now() + ttl
        raw = json.dumps(value) if not isinstance(value, str) else value
        with self._lock:
            with sqlite3.connect(self.path) as conn:
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

    def evict_expired(self) -> int:
        """Manually purge expired entries. Returns number of rows removed."""
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                cursor = conn.execute(
                    "DELETE FROM cache WHERE expires_at <= ?",
                    (self._now(),),
                )
                conn.commit()
                return cursor.rowcount


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
    if url:
        return RedisCache(url, prefix=prefix)
    # Prefer SQLite over in-memory TTLCache for persistence across restarts.
    cache_path = _default_sqlite_path()
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    return SQLiteCache(path=cache_path, ttl_seconds=default_ttl)
