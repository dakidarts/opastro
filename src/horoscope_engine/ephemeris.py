from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

import swisseph as swe

from .config import EphemerisConfig
from .models import (
    ArabicPartPosition,
    BodyPosition,
    ChartSnapshot,
    Aspect,
    FixedStarPosition,
)


logger = logging.getLogger(__name__)
SWE_LOCK = threading.Lock()


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


# Candidate minor bodies.  We probe each one at import time and keep only
# those whose ephemeris data is available.  This avoids noisy RuntimeWarning
# spew for users who haven't downloaded the optional ``seas_18.se1`` file.
_MINOR_BODY_CANDIDATES: list[BodySpec] = [
    BodySpec("Chiron", swe.CHIRON, "minor"),
    BodySpec("Ceres", swe.CERES, "asteroid"),
    BodySpec("North Node", None, "node"),
    BodySpec("South Node", None, "node"),
    BodySpec("Lilith", swe.MEAN_APOG, "minor"),
    BodySpec("Pallas", swe.PALLAS, "asteroid"),
    BodySpec("Juno", swe.JUNO, "asteroid"),
    BodySpec("Vesta", swe.VESTA, "asteroid"),
    BodySpec("Eris", getattr(swe, "ERIS", swe.AST_OFFSET + 136199), "dwarf"),
]


def _probe_minor_body(body: BodySpec) -> bool:
    """Return ``True`` if ``body`` can be calculated with current ephemeris."""
    if body.swe_id is None:
        return True
    try:
        test_jd = swe.julday(2024, 1, 1, 12.0)
        swe.calc_ut(test_jd, body.swe_id, swe.FLG_SWIEPH)
        return True
    except swe.Error:
        # Try Moshier fallback (built-in, no extra files).
        try:
            swe.calc_ut(test_jd, body.swe_id, swe.FLG_MOSEPH)
            return True
        except swe.Error:
            logger.debug(
                "Minor body %s (id=%s) unavailable with current ephemeris files. "
                "Run 'opastro doctor --download-ephemeris' to fetch optional files.",
                body.name,
                body.swe_id,
            )
            return False


# Build the runtime list of minor bodies once at import time.
MINOR_BODIES: list[BodySpec] = []
for _body in _MINOR_BODY_CANDIDATES:
    if _body.name in ("North Node", "South Node"):
        MINOR_BODIES.append(_body)
        continue
    if _probe_minor_body(_body):
        MINOR_BODIES.append(_body)


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

# Fixed stars supported by Swiss Ephemeris (name, SE star name, magnitude, nature, orb)
FIXED_STARS = [
    ("Regulus", "Regulus", 1.35, "mixed", 2.0),
    ("Spica", "Spica", 0.98, "benefic", 2.0),
    ("Algol", "Algol", 2.12, "malefic", 1.5),
    ("Antares", "Antares", 0.96, "malefic", 2.0),
    ("Aldebaran", "Aldebaran", 0.85, "malefic", 2.0),
    ("Pollux", "Pollux", 1.14, "mixed", 1.5),
    ("Vega", "Vega", 0.03, "benefic", 2.0),
    ("Sirius", "Sirius", -1.46, "benefic", 2.0),
    ("Arcturus", "Arcturus", -0.05, "benefic", 2.0),
    ("Deneb Algedi", "Deneb Algedi", 2.85, "mixed", 1.5),
]


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

    def _calc_body(
        self, body: BodySpec, jd: float, flags: int
    ) -> Tuple[float, float, float]:
        if body.swe_id is None:
            raise ValueError("Body requires derived longitude")
        try:
            result, _ = swe.calc_ut(jd, body.swe_id, flags)
        except swe.Error:
            # Fallback when Swiss ephemeris files are not available in runtime.
            result, _ = swe.calc_ut(
                jd, body.swe_id, (flags & ~swe.FLG_SWIEPH) | swe.FLG_MOSEPH
            )
        longitude = result[0]
        latitude = result[1]
        speed = result[3]
        return longitude, latitude, speed

    def _house_from_cusps(
        self, longitude: float, cusps: Sequence[float]
    ) -> Optional[int]:
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

    def get_positions(
        self, dt: datetime, ayanamsa_value: float
    ) -> Dict[str, BodyPosition]:
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
                # Already probed at import time, but guard against race
                # conditions or path changes after engine creation.
                logger.debug("Skipping %s: calculation failed at runtime.", body.name)
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

    def get_fixed_stars(self, dt: datetime) -> List[FixedStarPosition]:
        jd = self.datetime_to_julian(dt)
        stars: List[FixedStarPosition] = []
        for display_name, se_name, magnitude, nature, orb in FIXED_STARS:
            try:
                result = swe.fixstar2_ut(se_name, jd)
                # result = ((longitude, latitude, ...), star_name)
                data = (
                    result[0]
                    if isinstance(result, tuple) and len(result) > 1
                    else result
                )
                longitude = float(data[0])
                latitude = float(data[1])
                sign, degree = self._longitude_to_sign(longitude)
                stars.append(
                    FixedStarPosition(
                        name=display_name,
                        longitude=round(longitude, 6),
                        latitude=round(latitude, 6),
                        sign=sign,
                        degree_in_sign=round(degree, 3),
                        magnitude=magnitude,
                        nature=nature,
                        orb=orb,
                    )
                )
            except swe.Error:
                continue
        return stars

    def get_arabic_parts(
        self, positions: Dict[str, BodyPosition], ascendant: float
    ) -> List[ArabicPartPosition]:
        """Calculate key Arabic parts from a completed natal snapshot.

        Part of Fortune = Ascendant + Moon - Sun (day birth)
                        = Ascendant + Sun - Moon (night birth)
        Part of Spirit  = Ascendant + Sun - Moon (day birth)
                        = Ascendant + Moon - Sun (night birth)
        """
        parts: List[ArabicPartPosition] = []
        sun = positions.get("Sun")
        moon = positions.get("Moon")
        if sun is None or moon is None:
            return parts

        sun_lon = sun.longitude
        moon_lon = moon.longitude

        # Day birth if Sun is above the ascendant/descendant axis (simplified)
        is_day = abs((sun_lon - ascendant) % 360) < 180

        if is_day:
            pof_lon = (ascendant + moon_lon - sun_lon) % 360
            pos_lon = (ascendant + sun_lon - moon_lon) % 360
        else:
            pof_lon = (ascendant + sun_lon - moon_lon) % 360
            pos_lon = (ascendant + moon_lon - sun_lon) % 360

        pof_sign, pof_deg = self._longitude_to_sign(pof_lon)
        pos_sign, pos_deg = self._longitude_to_sign(pos_lon)

        parts.append(
            ArabicPartPosition(
                name="Part of Fortune",
                longitude=round(pof_lon, 6),
                sign=pof_sign,
                degree_in_sign=round(pof_deg, 3),
                formula="Asc + Moon - Sun" if is_day else "Asc + Sun - Moon",
            )
        )
        parts.append(
            ArabicPartPosition(
                name="Part of Spirit",
                longitude=round(pos_lon, 6),
                sign=pos_sign,
                degree_in_sign=round(pos_deg, 3),
                formula="Asc + Sun - Moon" if is_day else "Asc + Moon - Sun",
            )
        )
        return parts

    def chart_snapshot(
        self,
        dt: datetime,
        include_houses: bool = False,
        coordinates: Optional[Tuple[float, float]] = None,
        include_fixed_stars: bool = False,
        include_arabic_parts: bool = False,
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
            ascendant = 0.0

            if include_houses and coordinates:
                lat, lon = coordinates
                flags = self._flags(sidereal=not self._use_tropical())
                cusps, ascmc = swe.houses_ex(
                    jd, lat, lon, self.config.house_system.encode(), flags
                )
                ascendant = ascmc[0]
                rising_sign, _ = self._longitude_to_sign(ascendant)
                house_system = self.config.house_system
                house_cusps = [round(float(cusp), 6) for cusp in cusps[:12]]
                for position in positions.values():
                    position.house = self._house_from_cusps(
                        position.longitude, house_cusps
                    )

            aspects = self._calc_aspects(positions)
            ayanamsa_name = swe.get_ayanamsa_name(self.config.sidereal_mode)

            fixed_stars: List[FixedStarPosition] = []
            if include_fixed_stars:
                fixed_stars = self.get_fixed_stars(dt)

            arabic_parts: List[ArabicPartPosition] = []
            if include_arabic_parts and include_houses:
                arabic_parts = self.get_arabic_parts(positions, ascendant)

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
            fixed_stars=fixed_stars,
            arabic_parts=arabic_parts,
        )
