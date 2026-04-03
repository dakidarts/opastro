from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import threading
from typing import Any, Dict, Optional, Protocol

import os

import redis


@dataclass
class CacheItem:
    expires_at: datetime
    value: Any


class CacheProvider(Protocol):
    def get(self, key: str) -> Optional[Any]:
        ...

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ...


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
            self._store[key] = CacheItem(expires_at=datetime.utcnow() + ttl, value=value)


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


def cache_from_env(default_ttl: int) -> CacheProvider:
    url = os.getenv("REDIS_URL")
    prefix = os.getenv("REDIS_KEY_PREFIX", "")
    if url:
        return RedisCache(url, prefix=prefix)
    return TTLCache(default_ttl)
