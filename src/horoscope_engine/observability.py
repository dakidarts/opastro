from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
import json
import logging
import threading
import uuid
from typing import Any, Dict, Optional


@dataclass
class MetricsSnapshot:
    cache_hits: int
    cache_misses: int
    requests: int
    avg_latency_ms: float


class MetricsCollector:
    def __init__(self) -> None:
        self.cache_hits = 0
        self.cache_misses = 0
        self.requests = 0
        self.total_latency = 0.0
        self._lock = threading.Lock()

    def record_cache_hit(self) -> None:
        with self._lock:
            self.cache_hits += 1

    def record_cache_miss(self) -> None:
        with self._lock:
            self.cache_misses += 1

    def record_request(self, latency_ms: float) -> None:
        with self._lock:
            self.requests += 1
            self.total_latency += latency_ms

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            cache_hits = self.cache_hits
            cache_misses = self.cache_misses
            requests = self.requests
            total_latency = self.total_latency
        avg = total_latency / requests if requests else 0.0
        return MetricsSnapshot(
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            requests=requests,
            avg_latency_ms=round(avg, 3),
        )


class Timer:
    def __init__(self) -> None:
        self._start = perf_counter()

    def elapsed_ms(self) -> float:
        return (perf_counter() - self._start) * 1000.0


class StructuredLogger:
    """Production-grade structured JSON logger with request context.

    Example:
        log = StructuredLogger("opastro.api")
        log.info("Horoscope generated", sign="ARIES", latency_ms=42.5)
    """

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)
        self._context = threading.local()

    def _emit(self, level: int, message: str, **kwargs: Any) -> None:
        record: Dict[str, Any] = {
            "message": message,
            "level": logging.getLevelName(level),
            "timestamp": perf_counter(),
        }
        request_id = getattr(self._context, "request_id", None)
        if request_id:
            record["request_id"] = request_id
        tenant_id = getattr(self._context, "tenant_id", None)
        if tenant_id:
            record["tenant_id"] = tenant_id
        record.update(kwargs)
        self._logger.log(level, json.dumps(record, default=str))

    def set_context(
        self, *, request_id: Optional[str] = None, tenant_id: Optional[str] = None
    ) -> None:
        self._context.request_id = request_id
        self._context.tenant_id = tenant_id

    def clear_context(self) -> None:
        self._context.request_id = None
        self._context.tenant_id = None

    def debug(self, message: str, **kwargs: Any) -> None:
        self._emit(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._emit(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._emit(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._emit(logging.ERROR, message, **kwargs)


def generate_request_id() -> str:
    return str(uuid.uuid4())
