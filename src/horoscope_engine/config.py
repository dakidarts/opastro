from __future__ import annotations

import os
import site
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import swisseph as swe


def _default_ephemeris_path() -> Optional[str]:
    configured = os.getenv("SE_EPHE_PATH")
    if configured:
        return configured
    local = Path(__file__).resolve().parents[2] / "data" / "ephemeris"
    if local.exists():
        return str(local)
    # Auto-detect bundled Swiss files from common Python package installs (e.g. kerykeion).
    try:
        for base in site.getsitepackages():
            candidate = Path(base) / "kerykeion" / "sweph"
            if candidate.exists():
                return str(candidate)
    except Exception:
        pass
    return None


@dataclass(frozen=True)
class EphemerisConfig:
    ephemeris_path: Optional[str] = field(default_factory=_default_ephemeris_path)
    sidereal_mode: int = swe.SIDM_LAHIRI
    ayanamsa_system: str = "lahiri"
    zodiac_system: str = "tropical"
    house_system: str = "P"
    node_type: str = "true"
    orb_major: float = 8.0
    orb_sextile: float = 6.0
    orb_minor: float = 3.0
    aspect_exact_orb: float = 1.0


@dataclass(frozen=True)
class ServiceConfig:
    cache_ttl_seconds: int = 3600
    default_timezone: str = "UTC"
    default_latitude: float = 0.0
    default_longitude: float = 0.0
    content_strict_mode: bool = False
    content_root: Optional[str] = None
    ephemeris: EphemerisConfig = EphemerisConfig()
