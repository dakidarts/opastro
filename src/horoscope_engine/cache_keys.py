from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Optional, Sequence

from .models import Period


def _normalize_sections(sections: Optional[Sequence[str]]) -> str:
    if not sections:
        return "default"
    normalized = sorted(
        {str(section).strip().lower() for section in sections if str(section).strip()}
    )
    return ",".join(normalized) if normalized else "default"


def _format_coord(value: Optional[float]) -> str:
    if value is None:
        return "none"
    return f"{value:.6f}"


def _birth_signature(
    birth_date: Optional[str],
    birth_time: Optional[str],
    birth_latitude: Optional[float],
    birth_longitude: Optional[float],
    birth_timezone: Optional[str],
) -> str:
    if (
        birth_date is None
        and birth_time is None
        and birth_latitude is None
        and birth_longitude is None
        and birth_timezone is None
    ):
        return "none"
    return (
        f"{birth_date or 'none'}|{birth_time or 'none'}|"
        f"{_format_coord(birth_latitude)},{_format_coord(birth_longitude)}|"
        f"{birth_timezone or 'none'}"
    )


def build_cache_key(
    *,
    tenant_id: Optional[str],
    period: Period,
    sign: Optional[str],
    sign_source: Optional[str],
    sections: Optional[Sequence[str]],
    target_date: Optional[date],
    birth_date: Optional[str],
    birth_time: Optional[str],
    birth_latitude: Optional[float],
    birth_longitude: Optional[float],
    birth_timezone: Optional[str],
    zodiac_system: Optional[str],
    ayanamsa: Optional[str],
    house_system: Optional[str],
    node_type: Optional[str],
    user_name: Optional[str] = None,
    include_fixed_stars: bool = False,
    include_arabic_parts: bool = False,
    key_namespace: str = "horoscope",
) -> str:
    tenant = tenant_id or "public"
    date_part = target_date.isoformat() if target_date else "none"
    source = sign_source or ("provided" if sign else "derived")
    sections_key = _normalize_sections(sections)
    birth_key = _birth_signature(
        birth_date=birth_date,
        birth_time=birth_time,
        birth_latitude=birth_latitude,
        birth_longitude=birth_longitude,
        birth_timezone=birth_timezone,
    )
    extras = ""
    if include_fixed_stars:
        extras += ":fs"
    if include_arabic_parts:
        extras += ":ap"
    return (
        f"{key_namespace}:{tenant}:{period.value}:{source}:{sign or 'auto'}:{date_part}:"
        f"{sections_key}:{birth_key}:"
        f"{zodiac_system or 'default'}:{ayanamsa or 'default'}:{house_system or 'default'}:{node_type or 'default'}:"
        f"{(user_name or 'none').strip() or 'none'}{extras}"
    ).lower()


def build_model_cache_key(
    *, model: Any, tenant_id: Optional[str], key_namespace: str
) -> str:
    """Build a collision-resistant key from a complete Pydantic request model."""
    if not hasattr(model, "model_dump"):
        raise TypeError("model must provide model_dump()")

    payload = model.model_dump(mode="json", exclude={"tenant_id"})
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    request_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    tenant_value = (tenant_id or "public").strip() or "public"
    tenant_digest = hashlib.sha256(tenant_value.encode("utf-8")).hexdigest()[:16]
    return f"{key_namespace}:v2:{tenant_digest}:{request_digest}"
