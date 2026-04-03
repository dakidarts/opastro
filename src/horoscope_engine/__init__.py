"""NumerologyAPI Horoscope Engine."""

try:  # pragma: no cover - optional for lightweight tooling imports without pydantic runtime.
    from .models import HoroscopeRequest, HoroscopeResponse
except Exception:  # pragma: no cover
    HoroscopeRequest = None  # type: ignore[assignment]
    HoroscopeResponse = None  # type: ignore[assignment]

try:  # pragma: no cover - optional for lightweight tooling imports without swisseph runtime.
    from .service import HoroscopeService
except Exception:  # pragma: no cover
    HoroscopeService = None  # type: ignore[assignment]

__all__ = ["HoroscopeService", "HoroscopeRequest", "HoroscopeResponse"]
