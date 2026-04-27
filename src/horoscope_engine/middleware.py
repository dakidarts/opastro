from __future__ import annotations

import os
import time
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter keyed by tenant/API key.

    Configure via env:
        OPASTRO_RATE_LIMIT_RPS=10   # requests per second per key
        OPASTRO_RATE_LIMIT_BURST=20 # burst bucket size
    """

    def __init__(self, app, rps: Optional[float] = None, burst: Optional[int] = None):
        super().__init__(app)
        self.rps = rps or float(os.getenv("OPASTRO_RATE_LIMIT_RPS", "10"))
        self.burst = burst or int(os.getenv("OPASTRO_RATE_LIMIT_BURST", "20"))
        self._buckets: dict[
            str, tuple[float, float]
        ] = {}  # key -> (tokens, last_update)
        self._lock = __import__("threading").Lock()

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in {"/health", "/metrics"}:
            return await call_next(request)

        key = self._resolve_key(request)
        if not self._allow(key):
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "type": "rate_limit_exceeded",
                        "message": "Too many requests. Please slow down.",
                    }
                },
            )
        return await call_next(request)

    def _resolve_key(self, request: Request) -> str:
        api_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
        if api_key:
            return f"api:{api_key}"
        tenant = request.headers.get("X-Tenant-Id") or request.headers.get(
            "x-tenant-id"
        )
        if tenant:
            return f"tenant:{tenant}"
        # Fall back to client IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"

    def _allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.burst, now))
            elapsed = now - last
            tokens = min(self.burst, tokens + elapsed * self.rps)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return True
            self._buckets[key] = (tokens, now)
            return False


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Optional API key validation.

    Configure via env:
        OPASTRO_API_KEYS=pk_abc,pk_def   # comma-separated valid keys
        OPASTRO_REQUIRE_API_KEY=0        # set to 1 to enforce
    """

    def __init__(self, app):
        super().__init__(app)
        raw = os.getenv("OPASTRO_API_KEYS", "")
        self._valid_keys = {k.strip() for k in raw.split(",") if k.strip()}
        self._required = os.getenv("OPASTRO_REQUIRE_API_KEY", "0") == "1"

    async def dispatch(self, request: Request, call_next):
        if not self._required or not self._valid_keys:
            return await call_next(request)
        # Allow health/metrics unauthenticated
        if request.url.path in {"/health", "/metrics"}:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
        if not api_key or api_key not in self._valid_keys:
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "type": "unauthorized",
                        "message": "Invalid or missing API key.",
                    }
                },
            )
        return await call_next(request)
