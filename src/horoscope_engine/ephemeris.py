from __future__ import annotations

import threading
import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

import swisseph as swe

from .config import EphemerisConfig
from .models import BodyPosition, ChartSnapshot, Aspect


SWE_LOCK = threading.Lock()
MISSING_BODY_WARNED: set[str] = set()


@dataclass(frozen=True)
class BodySpec:
    name: str
    swe_id: Optional[int]
    kind: str


MAJOR_BODIES = [
    BodySpec("Sun", swe.SUN, "planet"),
    BodySpec("Moon", swe.MOON, "planet"),
    BodySpec("Mercury", swe.MERCURY, "planet"),
    BodySpec("Venus", swe.VENUS, "planet"),
    BodySpec("Mars", swe.MARS, "planet"),
    BodySpec("Jupiter", swe.JUPITER, "planet"),
    BodySpec("Saturn", swe.SATURN, "planet"),
    BodySpec("Uranus", swe.URANUS, "planet"),
    BodySpec("Neptune", swe.NEPTUNE, "planet"),
    BodySpec("Pluto", swe.PLUTO, "planet"),
]

MINOR_BODIES = [
    BodySpec("Chiron", swe.CHIRON, "minor"),
    BodySpec("Ceres", swe.CERES, "asteroid"),
    BodySpec("North Node", None, "node"),
    BodySpec("South Node", None, "node"),
    BodySpec("Lilith", swe.MEAN_APOG, "minor"),
    BodySpec("Pallas", swe.PALLAS, "asteroid"),
    BodySpec("Juno", swe.JUNO, "asteroid"),
    BodySpec("Vesta", swe.VESTA, "asteroid"),
    # Fallback to asteroid number when ERIS constant is unavailable in the local swisseph build.
    BodySpec("Eris", getattr(swe, "ERIS", swe.AST_OFFSET + 136199), "dwarf"),
]

ASPECTS = {
    "conjunction": (0.0, "major"),
    "opposition": (180.0, "major"),
    "trine": (120.0, "major"),
    "square": (90.0, "major"),
    "sextile": (60.0, "sextile"),
    "quincunx": (150.0, "minor"),
    "semi-sextile": (30.0, "minor"),
    "semi-square": (45.0, "minor"),
    "sesquiquadrate": (135.0, "minor"),
}


class EphemerisEngine:
    def __init__(self, config: EphemerisConfig):
        self.config = config
        if config.ephemeris_path:
            swe.set_ephe_path(config.ephemeris_path)
        self._node_id = swe.TRUE_NODE if config.node_type == "true" else swe.MEAN_NODE

    def datetime_to_julian(self, dt: datetime) -> float:
        return swe.julday(
            dt.year,
            dt.month,
            dt.day,
            dt.hour + dt.minute / 60.0 + dt.second / 3600.0,
        )

    def _flags(self, sidereal: bool) -> int:
        flags = swe.FLG_SWIEPH | swe.FLG_SPEED
        if sidereal:
            flags |= swe.FLG_SIDEREAL
        return flags

    def _use_tropical(self) -> bool:
        return (self.config.zodiac_system or "tropical").lower() == "tropical"

    def _longitude_to_sign(self, longitude: float) -> Tuple[str, float]:
        normalized = longitude % 360.0
        index = int(normalized // 30)
        degree_in_sign = normalized % 30.0
        signs = [
            "ARIES",
            "TAURUS",
            "GEMINI",
            "CANCER",
            "LEO",
            "VIRGO",
            "LIBRA",
            "SCORPIO",
            "SAGITTARIUS",
            "CAPRICORN",
            "AQUARIUS",
            "PISCES",
        ]
        return signs[index], degree_in_sign

    def _calc_body(self, body: BodySpec, jd: float, flags: int) -> Tuple[float, float, float]:
        if body.swe_id is None:
            raise ValueError("Body requires derived longitude")
        try:
            result, _ = swe.calc_ut(jd, body.swe_id, flags)
        except swe.Error:
            # Fallback when Swiss ephemeris files are not available in runtime.
            result, _ = swe.calc_ut(jd, body.swe_id, (flags & ~swe.FLG_SWIEPH) | swe.FLG_MOSEPH)
        longitude = result[0]
        latitude = result[1]
        speed = result[3]
        return longitude, latitude, speed

    def _house_from_cusps(self, longitude: float, cusps: Sequence[float]) -> Optional[int]:
        if len(cusps) != 12:
            return None
        lon = longitude % 360.0
        normalized = [(cusp % 360.0) for cusp in cusps]
        for idx in range(12):
            start = normalized[idx]
            end = normalized[(idx + 1) % 12]
            arc = (end - start) % 360.0
            if arc <= 0:
                continue
            offset = (lon - start) % 360.0
            if offset < arc or (idx == 11 and offset <= arc):
                return idx + 1
        return None

    def get_positions(self, dt: datetime, ayanamsa_value: float) -> Dict[str, BodyPosition]:
        jd = self.datetime_to_julian(dt)
        positions: Dict[str, BodyPosition] = {}
        tropical_flags = self._flags(sidereal=False)
        sidereal_flags = self._flags(sidereal=True)

        for body in MAJOR_BODIES + MINOR_BODIES:
            if body.name in ("North Node", "South Node"):
                lon_t, _, _ = self._calc_body(
                    BodySpec("North Node", self._node_id, "node"), jd, tropical_flags
                )
                lon_s, lat_s, speed_s = self._calc_body(
                    BodySpec("North Node", self._node_id, "node"), jd, sidereal_flags
                )
                if body.name == "South Node":
                    lon_t = (lon_t + 180.0) % 360.0
                    lon_s = (lon_s + 180.0) % 360.0
                trop_sign, _ = self._longitude_to_sign(lon_t)
                sid_sign, _ = self._longitude_to_sign(lon_s)
                active_lon = lon_t if self._use_tropical() else lon_s
                active_sign, active_degree = self._longitude_to_sign(active_lon)
                positions[body.name] = BodyPosition(
                    name=body.name,
                    longitude=active_lon,
                    tropical_longitude=lon_t,
                    sidereal_longitude=lon_s,
                    latitude=lat_s,
                    speed=speed_s,
                    sign=active_sign,
                    tropical_sign=trop_sign,
                    sidereal_sign=sid_sign,
                    degree_in_sign=active_degree,
                    retrograde=speed_s < 0,
                    ayanamsa_value=ayanamsa_value,
                )
                continue
            if body.swe_id is None:
                continue

            try:
                lon_t, _, _ = self._calc_body(body, jd, tropical_flags)
                lon_s, lat_s, speed_s = self._calc_body(body, jd, sidereal_flags)
            except swe.Error:
                if body.name in {"Chiron", "Pallas", "Juno", "Vesta", "Eris"} and body.name not in MISSING_BODY_WARNED:
                    warnings.warn(
                        f"Skipping {body.name}: Swiss Ephemeris data not available for this body at current ephemeris path.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    MISSING_BODY_WARNED.add(body.name)
                continue
            trop_sign, _ = self._longitude_to_sign(lon_t)
            sid_sign, _ = self._longitude_to_sign(lon_s)
            active_lon = lon_t if self._use_tropical() else lon_s
            active_sign, active_degree = self._longitude_to_sign(active_lon)
            positions[body.name] = BodyPosition(
                name=body.name,
                longitude=active_lon,
                tropical_longitude=lon_t,
                sidereal_longitude=lon_s,
                latitude=lat_s,
                speed=speed_s,
                sign=active_sign,
                tropical_sign=trop_sign,
                sidereal_sign=sid_sign,
                degree_in_sign=active_degree,
                retrograde=speed_s < 0,
                ayanamsa_value=ayanamsa_value,
            )

        return positions

    def _calc_aspects(self, positions: Dict[str, BodyPosition]) -> List[Aspect]:
        names = list(positions.keys())
        aspects: List[Aspect] = []
        for i, name1 in enumerate(names):
            for name2 in names[i + 1 :]:
                p1 = positions[name1]
                p2 = positions[name2]
                angle = abs(p1.longitude - p2.longitude)
                if angle > 180:
                    angle = 360 - angle

                for aspect_name, (target, tier) in ASPECTS.items():
                    if tier == "sextile":
                        orb_limit = self.config.orb_sextile
                    elif tier == "minor":
                        orb_limit = self.config.orb_minor
                    else:
                        orb_limit = self.config.orb_major
                    diff = abs(angle - target)
                    if diff <= orb_limit:
                        aspects.append(
                            Aspect(
                                body1=name1,
                                body2=name2,
                                aspect=aspect_name,
                                orb=round(diff, 2),
                                exact=diff <= self.config.aspect_exact_orb,
                                applying=False,
                            )
                        )
        return aspects

    def chart_snapshot(
        self,
        dt: datetime,
        include_houses: bool = False,
        coordinates: Optional[Tuple[float, float]] = None,
    ) -> ChartSnapshot:
        with SWE_LOCK:
            swe.set_sid_mode(self.config.sidereal_mode, 0, 0)
            jd = self.datetime_to_julian(dt)
            ayanamsa_value = swe.get_ayanamsa(jd)
            positions = self.get_positions(dt, ayanamsa_value)
            sun_sign = positions["Sun"].sign
            moon_sign = positions["Moon"].sign
            rising_sign = None
            house_system = None
            house_cusps: Optional[List[float]] = None

            if include_houses and coordinates:
                lat, lon = coordinates
                flags = self._flags(sidereal=not self._use_tropical())
                cusps, ascmc = swe.houses_ex(jd, lat, lon, self.config.house_system.encode(), flags)
                asc_long = ascmc[0]
                rising_sign, _ = self._longitude_to_sign(asc_long)
                house_system = self.config.house_system
                house_cusps = [round(float(cusp), 6) for cusp in cusps[:12]]
                for position in positions.values():
                    position.house = self._house_from_cusps(position.longitude, house_cusps)

            aspects = self._calc_aspects(positions)
            ayanamsa_name = swe.get_ayanamsa_name(self.config.sidereal_mode)

        return ChartSnapshot(
            timestamp=dt,
            zodiac_system=self.config.zodiac_system,
            ayanamsa=ayanamsa_name,
            ayanamsa_value=round(ayanamsa_value, 6),
            ayanamsa_system=self.config.ayanamsa_system,
            sun_sign=sun_sign,
            moon_sign=moon_sign,
            rising_sign=rising_sign,
            house_system=house_system,
            house_cusps=house_cusps,
            positions=list(positions.values()),
            aspects=aspects,
        )
