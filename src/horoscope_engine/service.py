from __future__ import annotations

from datetime import date, datetime, time, timedelta
from itertools import combinations
from pathlib import Path
from typing import List, Optional, Tuple

import swisseph as swe

from .aggregation import aggregate_period
from .config import ServiceConfig, EphemerisConfig
from .content_repository import V2ContentRepository
from .ephemeris import EphemerisEngine
from .interpretation.renderer import InterpretationEngine
from .interpretation.rules import load_rules
from .models import (
    BirthData,
    BirthdayHoroscopeRequest,
    HoroscopeRequest,
    HoroscopeResponse,
    NatalBirthchartRequest,
    NatalBirthchartResponse,
    NatalDominantSignature,
    NatalAspectPattern,
    NatalPlanetCondition,
    NatalPremiumInsights,
    Period,
    PeriodCelestialData,
    PlanetHoroscopeRequest,
    PlanetName,
    ReportType,
    Section,
    AyanamsaSystem,
    HouseSystem,
    NodeType,
    ZodiacSystem,
    ZODIAC_SIGNS,
    ChartSnapshot,
)

BIRTHDAY_FACTOR_ALLOWLIST = [
    "yearly_theme_archetypes",
    "yearly_house_focus",
    "planetary_focus",
    "transits_archetypes",
    "aspects",
]

PLANET_BODY_MAP = {
    PlanetName.SUN: "Sun",
    PlanetName.MOON: "Moon",
    PlanetName.MERCURY: "Mercury",
    PlanetName.VENUS: "Venus",
    PlanetName.MARS: "Mars",
    PlanetName.JUPITER: "Jupiter",
    PlanetName.SATURN: "Saturn",
    PlanetName.URANUS: "Uranus",
    PlanetName.NEPTUNE: "Neptune",
    PlanetName.PLUTO: "Pluto",
    PlanetName.CHIRON: "Chiron",
}

PLANET_FACTOR_ALLOWLIST_BY_PERIOD = {
    Period.DAILY: [
        "transits_archetypes",
        "aspects",
        "daily_house_focus",
    ],
    Period.WEEKLY: [
        "planetary_focus",
        "transits_archetypes",
        "aspects",
        "weekly_house_focus",
        "weekly_theme_archetypes",
        "weekly_moon_phase",
    ],
    Period.MONTHLY: [
        "planetary_focus",
        "transits_archetypes",
        "aspects",
        "monthly_house_focus",
        "monthly_theme_archetypes",
        "monthly_lunation_archetypes",
        "eclipse_archetypes",
        "retrograde_archetypes",
        "ingress_archetypes",
    ],
    Period.YEARLY: [
        "planetary_focus",
        "transits_archetypes",
        "aspects",
        "yearly_house_focus",
        "yearly_theme_archetypes",
        "eclipse_archetypes",
        "outer_planet_focus",
        "nodal_axis",
    ],
}

SIGN_TO_ELEMENT = {
    "ARIES": "fire",
    "TAURUS": "earth",
    "GEMINI": "air",
    "CANCER": "water",
    "LEO": "fire",
    "VIRGO": "earth",
    "LIBRA": "air",
    "SCORPIO": "water",
    "SAGITTARIUS": "fire",
    "CAPRICORN": "earth",
    "AQUARIUS": "air",
    "PISCES": "water",
}

SIGN_TO_MODALITY = {
    "ARIES": "cardinal",
    "CANCER": "cardinal",
    "LIBRA": "cardinal",
    "CAPRICORN": "cardinal",
    "TAURUS": "fixed",
    "LEO": "fixed",
    "SCORPIO": "fixed",
    "AQUARIUS": "fixed",
    "GEMINI": "mutable",
    "VIRGO": "mutable",
    "SAGITTARIUS": "mutable",
    "PISCES": "mutable",
}

SIGN_TO_OPPOSITE = {
    "ARIES": "LIBRA",
    "TAURUS": "SCORPIO",
    "GEMINI": "SAGITTARIUS",
    "CANCER": "CAPRICORN",
    "LEO": "AQUARIUS",
    "VIRGO": "PISCES",
    "LIBRA": "ARIES",
    "SCORPIO": "TAURUS",
    "SAGITTARIUS": "GEMINI",
    "CAPRICORN": "CANCER",
    "AQUARIUS": "LEO",
    "PISCES": "VIRGO",
}

SIGN_RULERS = {
    "ARIES": {"Mars"},
    "TAURUS": {"Venus"},
    "GEMINI": {"Mercury"},
    "CANCER": {"Moon"},
    "LEO": {"Sun"},
    "VIRGO": {"Mercury"},
    "LIBRA": {"Venus"},
    "SCORPIO": {"Pluto", "Mars"},
    "SAGITTARIUS": {"Jupiter"},
    "CAPRICORN": {"Saturn"},
    "AQUARIUS": {"Uranus", "Saturn"},
    "PISCES": {"Neptune", "Jupiter"},
}

FOCUS_PLANETS = {
    "Sun",
    "Moon",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
    "Pluto",
    "Chiron",
}


class HoroscopeService:
    def __init__(
        self,
        config: ServiceConfig,
        rules_path: Optional[Path] = None,
    ) -> None:
        self.config = config
        path = rules_path or Path(__file__).resolve().parent / "data" / "default_rules.json"
        if not path.exists():
            path = Path(__file__).resolve().parents[2] / "data" / "rules" / "default_rules.json"
        self.rules = load_rules(path)
        self.content_repository: Optional[V2ContentRepository] = None
        if config.content_root:
            self.content_repository = V2ContentRepository(Path(config.content_root))
        self.interpreter = InterpretationEngine(
            self.rules,
            self.content_repository,
            strict_content_mode=config.content_strict_mode,
        )
        self._default_ephemeris = EphemerisEngine(config.ephemeris)

        self._ayanamsa_map = {
            AyanamsaSystem.LAHIRI: ("lahiri", swe.SIDM_LAHIRI),
            AyanamsaSystem.FAGAN_BRADLEY: ("fagan_bradley", swe.SIDM_FAGAN_BRADLEY),
            AyanamsaSystem.KRISHNAMURTI: ("krishnamurti", swe.SIDM_KRISHNAMURTI),
            AyanamsaSystem.RAMAN: ("raman", swe.SIDM_RAMAN),
            AyanamsaSystem.YUKTESWAR: ("yukteswar", getattr(swe, "SIDM_YUKTESWAR", swe.SIDM_LAHIRI)),
        }
        self._house_map = {
            HouseSystem.PLACIDUS: "P",
            HouseSystem.WHOLE_SIGN: "W",
            HouseSystem.EQUAL: "E",
            HouseSystem.KOCH: "K",
        }

    def generate(self, request: HoroscopeRequest) -> HoroscopeResponse:
        ephemeris = self._resolve_ephemeris(request)
        target_sign = self._resolve_sign(request.sign, request.birth, ephemeris)
        start, end = self._resolve_period_range(request.period, request.target_date)
        include_houses = self._can_use_precise_houses(request.birth)
        coordinates = self._coords_tuple(request.birth) if include_houses else None
        natal_house_frame: Optional[ChartSnapshot] = None
        if include_houses and request.birth and coordinates:
            natal_house_frame = ephemeris.chart_snapshot(
                self._birth_datetime(request.birth),
                include_houses=True,
                coordinates=coordinates,
            )
        aggregation = aggregate_period(
            ephemeris,
            request.period,
            start,
            end,
            include_houses=include_houses,
            coordinates=coordinates,
        )
        snapshot = aggregation.snapshot
        if include_houses and natal_house_frame:
            self._apply_house_frame(snapshot, natal_house_frame)
        notable = aggregation.notable_events or self._build_notable_events(snapshot)
        factor_values = self.interpreter.calculate_period_factor_map(
            sign=target_sign,
            snapshot=snapshot,
            period=request.period,
            metrics=aggregation.metrics,
            period_events=aggregation.period_events,
        )
        data = PeriodCelestialData(
            period=request.period,
            start=start,
            end=end,
            snapshot=snapshot,
            metrics=aggregation.metrics,
            notable_events=notable,
            period_events=aggregation.period_events,
            factor_values=factor_values,
        )

        sections = request.sections or self._default_sections()
        insights = self.interpreter.build_section_insights(
            target_sign,
            snapshot,
            sections,
            request.period,
            aggregation.metrics,
            notable,
            aggregation.period_events,
        )

        return HoroscopeResponse(
            report_type=ReportType.HOROSCOPE,
            sign=target_sign,
            period=request.period,
            start=start,
            end=end,
            data=data,
            sections=insights,
        )

    def generate_birthday(self, request: BirthdayHoroscopeRequest) -> HoroscopeResponse:
        ephemeris = self._resolve_ephemeris(request)
        target_sign = self._resolve_sign(request.sign, request.birth, ephemeris)
        start, end = self._resolve_birthday_range(request.birth, request.target_date)
        include_houses = self._can_use_precise_houses(request.birth)
        coordinates = self._coords_tuple(request.birth) if include_houses else None
        natal_house_frame: Optional[ChartSnapshot] = None
        if include_houses and request.birth and coordinates:
            natal_house_frame = ephemeris.chart_snapshot(
                self._birth_datetime(request.birth),
                include_houses=True,
                coordinates=coordinates,
            )

        aggregation = aggregate_period(
            ephemeris,
            Period.YEARLY,
            start,
            end,
            include_houses=include_houses,
            coordinates=coordinates,
        )
        snapshot = aggregation.snapshot
        if include_houses and natal_house_frame:
            self._apply_house_frame(snapshot, natal_house_frame)
        notable = aggregation.notable_events or self._build_notable_events(snapshot)

        factor_values = self.interpreter.calculate_period_factor_map(
            sign=target_sign,
            snapshot=snapshot,
            period=Period.YEARLY,
            metrics=aggregation.metrics,
            period_events=aggregation.period_events,
            factor_type_allowlist=BIRTHDAY_FACTOR_ALLOWLIST,
        )
        data = PeriodCelestialData(
            period=Period.YEARLY,
            start=start,
            end=end,
            snapshot=snapshot,
            metrics=aggregation.metrics,
            notable_events=notable,
            period_events=aggregation.period_events,
            factor_values=factor_values,
        )

        sections = request.sections or self._default_sections()
        insights = self.interpreter.build_section_insights(
            target_sign,
            snapshot,
            sections,
            Period.YEARLY,
            aggregation.metrics,
            notable,
            aggregation.period_events,
            factor_type_allowlist=BIRTHDAY_FACTOR_ALLOWLIST,
        )

        return HoroscopeResponse(
            report_type=ReportType.BIRTHDAY,
            sign=target_sign,
            period=Period.YEARLY,
            start=start,
            end=end,
            data=data,
            sections=insights,
        )

    def generate_planet(self, request: PlanetHoroscopeRequest) -> HoroscopeResponse:
        ephemeris = self._resolve_ephemeris(request)
        target_sign = self._resolve_sign(request.sign, request.birth, ephemeris)
        start, end = self._resolve_period_range(request.period, request.target_date)
        include_houses = self._can_use_precise_houses(request.birth)
        coordinates = self._coords_tuple(request.birth) if include_houses else None
        natal_house_frame: Optional[ChartSnapshot] = None
        if include_houses and request.birth and coordinates:
            natal_house_frame = ephemeris.chart_snapshot(
                self._birth_datetime(request.birth),
                include_houses=True,
                coordinates=coordinates,
            )

        aggregation = aggregate_period(
            ephemeris,
            request.period,
            start,
            end,
            include_houses=include_houses,
            coordinates=coordinates,
        )
        snapshot = aggregation.snapshot
        if include_houses and natal_house_frame:
            self._apply_house_frame(snapshot, natal_house_frame)
        notable = aggregation.notable_events or self._build_notable_events(snapshot)

        focus_body = PLANET_BODY_MAP[request.planet]
        allowlist = PLANET_FACTOR_ALLOWLIST_BY_PERIOD[request.period]

        factor_values = self.interpreter.calculate_period_factor_map(
            sign=target_sign,
            snapshot=snapshot,
            period=request.period,
            metrics=aggregation.metrics,
            period_events=aggregation.period_events,
            factor_type_allowlist=allowlist,
            focus_body=focus_body,
        )
        data = PeriodCelestialData(
            period=request.period,
            start=start,
            end=end,
            snapshot=snapshot,
            metrics=aggregation.metrics,
            notable_events=notable,
            period_events=aggregation.period_events,
            factor_values=factor_values,
        )

        sections = request.sections or self._default_sections()
        insights = self.interpreter.build_section_insights(
            target_sign,
            snapshot,
            sections,
            request.period,
            aggregation.metrics,
            notable,
            aggregation.period_events,
            factor_type_allowlist=allowlist,
            focus_body=focus_body,
        )

        return HoroscopeResponse(
            report_type=ReportType.PLANET,
            sign=target_sign,
            period=request.period,
            start=start,
            end=end,
            data=data,
            sections=insights,
        )

    def generate_natal_birthchart(self, request: NatalBirthchartRequest) -> NatalBirthchartResponse:
        ephemeris = self._resolve_ephemeris(request)
        include_houses = self._can_use_precise_houses(request.birth)
        coordinates = self._coords_tuple(request.birth) if include_houses else None
        snapshot = ephemeris.chart_snapshot(
            self._birth_datetime(request.birth),
            include_houses=include_houses,
            coordinates=coordinates,
        )
        planet_conditions = self._natal_planet_conditions(snapshot)
        premium_insights = NatalPremiumInsights(
            dominant_signature=self._natal_dominant_signature(snapshot, planet_conditions),
            aspect_patterns=self._natal_aspect_patterns(snapshot),
            planet_conditions=planet_conditions,
        )
        return NatalBirthchartResponse(
            report_type=ReportType.NATAL_BIRTHCHART,
            sign=snapshot.sun_sign,
            birth=request.birth,
            snapshot=snapshot,
            notable_events=self._build_notable_events(snapshot),
            premium_insights=premium_insights,
        )

    def _resolve_sign(self, sign: Optional[str], birth: Optional[BirthData], ephemeris: EphemerisEngine) -> str:
        if sign:
            return sign
        if birth is None:
            raise ValueError("sign or birth data is required")
        birth_dt = self._birth_datetime(birth)
        snapshot = ephemeris.chart_snapshot(birth_dt)
        return snapshot.sun_sign

    def _can_use_precise_houses(self, birth: Optional[BirthData]) -> bool:
        if not birth:
            return False
        return bool(birth.time and birth.coordinates)

    def _resolve_ephemeris(
        self,
        request: HoroscopeRequest | BirthdayHoroscopeRequest | PlanetHoroscopeRequest | NatalBirthchartRequest,
    ) -> EphemerisEngine:
        if not request.zodiac_system and not request.ayanamsa and not request.house_system and not request.node_type:
            return self._default_ephemeris

        base = self.config.ephemeris
        ayanamsa_system = request.ayanamsa or AyanamsaSystem.LAHIRI
        ayanamsa_key, sidereal_mode = self._ayanamsa_map[ayanamsa_system]
        house_system = self._house_map.get(request.house_system or HouseSystem.PLACIDUS, base.house_system)
        node_type = (request.node_type or NodeType.TRUE).value
        zodiac_system = (request.zodiac_system or ZodiacSystem(base.zodiac_system)).value

        override = EphemerisConfig(
            ephemeris_path=base.ephemeris_path,
            sidereal_mode=sidereal_mode,
            ayanamsa_system=ayanamsa_key,
            zodiac_system=zodiac_system,
            house_system=house_system,
            node_type=node_type,
            orb_major=base.orb_major,
            orb_sextile=base.orb_sextile,
            orb_minor=base.orb_minor,
            aspect_exact_orb=base.aspect_exact_orb,
        )
        return EphemerisEngine(override)

    def _resolve_birthday_range(self, birth: Optional[BirthData], target_date: Optional[date]) -> Tuple[datetime, datetime]:
        if birth:
            base = target_date or date.today()
            month = birth.date.month
            day = birth.date.day
            start_date = self._safe_anniversary(base.year, month, day)
            if base < start_date:
                start_date = self._safe_anniversary(base.year - 1, month, day)
        else:
            if target_date is None:
                raise ValueError("For birthday reports, provide birth data or target_date.")
            start_date = target_date
            month = start_date.month
            day = start_date.day

        end_date = self._safe_anniversary(start_date.year + 1, month, day)
        return datetime.combine(start_date, time.min), datetime.combine(end_date, time.min)

    def _safe_anniversary(self, year: int, month: int, day: int) -> date:
        try:
            return date(year, month, day)
        except ValueError:
            if month == 2 and day == 29:
                return date(year, 2, 28)
            raise

    def _birth_datetime(self, birth: BirthData) -> datetime:
        if birth.time:
            hour, minute = map(int, birth.time.split(":"))
            birth_time = time(hour=hour, minute=minute)
        else:
            birth_time = time(hour=12, minute=0)
        return datetime.combine(birth.date, birth_time)

    def _coords_tuple(self, birth: Optional[BirthData]) -> Optional[Tuple[float, float]]:
        if not birth or not birth.coordinates:
            return None
        return (birth.coordinates.latitude, birth.coordinates.longitude)

    def _resolve_period_range(self, period: Period, target_date: Optional[date]) -> Tuple[datetime, datetime]:
        base = target_date or date.today()
        if period == Period.DAILY:
            start = datetime.combine(base, time.min)
            return start, start + timedelta(days=1)
        if period == Period.WEEKLY:
            start = datetime.combine(base - timedelta(days=base.weekday()), time.min)
            return start, start + timedelta(days=7)
        if period == Period.MONTHLY:
            start = datetime.combine(base.replace(day=1), time.min)
            if base.month == 12:
                end_date = date(base.year + 1, 1, 1)
            else:
                end_date = date(base.year, base.month + 1, 1)
            return start, datetime.combine(end_date, time.min)
        if period == Period.YEARLY:
            start = datetime.combine(date(base.year, 1, 1), time.min)
            return start, datetime.combine(date(base.year + 1, 1, 1), time.min)
        raise ValueError("Unsupported period")

    def _default_sections(self) -> List[Section]:
        return [
            Section.GENERAL,
            Section.LOVE_SINGLES,
            Section.LOVE_COUPLES,
            Section.CAREER,
            Section.FRIENDSHIP,
            Section.HEALTH,
            Section.MONEY,
            Section.COMMUNICATION,
            Section.LIFESTYLE,
        ]

    def _build_notable_events(self, snapshot) -> List[str]:
        events: List[str] = []
        for position in snapshot.positions:
            if position.retrograde:
                events.append(f"{position.name} retrograde in {position.sign}")
        events.append(f"Moon in {snapshot.moon_sign}")
        events.append(f"Sun in {snapshot.sun_sign}")
        return events

    def _apply_house_frame(self, snapshot: ChartSnapshot, natal_frame: ChartSnapshot) -> None:
        snapshot.rising_sign = natal_frame.rising_sign
        snapshot.house_system = natal_frame.house_system
        snapshot.house_cusps = natal_frame.house_cusps

        cusps = natal_frame.house_cusps or []
        for position in snapshot.positions:
            house = self._house_from_cusps(position.longitude, cusps)
            if house is None and snapshot.rising_sign:
                house = self._whole_sign_house(snapshot.rising_sign, position.sign)
            position.house = house

    def _house_from_cusps(self, longitude: float, cusps: List[float]) -> Optional[int]:
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

    def _whole_sign_house(self, rising_sign: str, target_sign: str) -> int:
        rising_idx = ZODIAC_SIGNS.index(rising_sign.upper())
        target_idx = ZODIAC_SIGNS.index(target_sign.upper())
        return ((target_idx - rising_idx) % 12) + 1

    def _natal_planet_conditions(self, snapshot: ChartSnapshot) -> List[NatalPlanetCondition]:
        planet_to_rulership_signs: dict[str, set[str]] = {}
        for sign, rulers in SIGN_RULERS.items():
            for ruler in rulers:
                planet_to_rulership_signs.setdefault(ruler, set()).add(sign)

        output: List[NatalPlanetCondition] = []
        for position in snapshot.positions:
            if position.name not in FOCUS_PLANETS:
                continue
            notes: List[str] = []
            strength = 1.0

            if position.house in {1, 4, 7, 10}:
                strength += 0.35
                notes.append("Angular house emphasis")
            elif position.house in {2, 5, 8, 11}:
                strength += 0.15
                notes.append("Succedent house support")
            elif position.house in {3, 6, 9, 12}:
                strength += 0.05
                notes.append("Cadent house adaptation")

            if position.retrograde:
                strength -= 0.2
                notes.append("Retrograde introspection")
            else:
                strength += 0.05

            if position.name in {"Sun", "Moon"}:
                strength += 0.05
                notes.append("Luminary weight")

            rulers_for_sign = SIGN_RULERS.get(position.sign, set())
            if position.name in rulers_for_sign:
                strength += 0.25
                notes.append("In domicile")

            detriment_signs = {
                SIGN_TO_OPPOSITE[ruling_sign]
                for ruling_sign in planet_to_rulership_signs.get(position.name, set())
                if ruling_sign in SIGN_TO_OPPOSITE
            }
            if position.sign in detriment_signs:
                strength -= 0.15
                notes.append("In detriment")

            output.append(
                NatalPlanetCondition(
                    planet=position.name,
                    sign=position.sign,
                    house=position.house,
                    retrograde=position.retrograde,
                    strength=round(max(0.05, strength), 3),
                    notes=notes,
                )
            )

        output.sort(key=lambda item: (-item.strength, item.planet))
        return output

    def _natal_dominant_signature(
        self,
        snapshot: ChartSnapshot,
        planet_conditions: List[NatalPlanetCondition],
    ) -> NatalDominantSignature:
        positions = [position for position in snapshot.positions if position.name in FOCUS_PLANETS]
        total = len(positions) or 1
        element_balance = {"fire": 0.0, "earth": 0.0, "air": 0.0, "water": 0.0}
        modality_balance = {"cardinal": 0.0, "fixed": 0.0, "mutable": 0.0}

        angular_counts = {"angular": 0.0, "succedent": 0.0, "cadent": 0.0}
        for position in positions:
            element = SIGN_TO_ELEMENT.get(position.sign)
            if element:
                element_balance[element] += 1.0
            modality = SIGN_TO_MODALITY.get(position.sign)
            if modality:
                modality_balance[modality] += 1.0

            if position.house in {1, 4, 7, 10}:
                angular_counts["angular"] += 1.0
            elif position.house in {2, 5, 8, 11}:
                angular_counts["succedent"] += 1.0
            elif position.house in {3, 6, 9, 12}:
                angular_counts["cadent"] += 1.0

        for key in element_balance:
            element_balance[key] = round(element_balance[key] / total, 3)
        for key in modality_balance:
            modality_balance[key] = round(modality_balance[key] / total, 3)
        for key in angular_counts:
            angular_counts[key] = round(angular_counts[key] / total, 3)

        dominant_element = max(element_balance, key=lambda key: (element_balance[key], key))
        dominant_modality = max(modality_balance, key=lambda key: (modality_balance[key], key))
        top_planets = [entry.planet for entry in planet_conditions[:3]]

        return NatalDominantSignature(
            element_balance=element_balance,
            modality_balance=modality_balance,
            dominant_element=dominant_element,
            dominant_modality=dominant_modality,
            angular_emphasis=angular_counts,
            top_planets=top_planets,
        )

    def _natal_aspect_patterns(self, snapshot: ChartSnapshot) -> List[NatalAspectPattern]:
        bodies = sorted({position.name for position in snapshot.positions if position.name in FOCUS_PLANETS})
        if not bodies:
            return []

        by_aspect: dict[str, set[frozenset[str]]] = {}
        for aspect in snapshot.aspects:
            if aspect.body1 not in FOCUS_PLANETS or aspect.body2 not in FOCUS_PLANETS:
                continue
            pair = frozenset({aspect.body1, aspect.body2})
            by_aspect.setdefault(aspect.aspect, set()).add(pair)

        trines = by_aspect.get("trine", set())
        squares = by_aspect.get("square", set())
        oppositions = by_aspect.get("opposition", set())
        sextiles = by_aspect.get("sextile", set())

        patterns: List[NatalAspectPattern] = []
        dedupe: set[tuple[str, tuple[str, ...]]] = set()

        for a, b, c in combinations(bodies, 3):
            pairs = [frozenset({a, b}), frozenset({a, c}), frozenset({b, c})]
            if all(pair in trines for pair in pairs):
                key = ("grand_trine", tuple(sorted((a, b, c))))
                if key not in dedupe:
                    dedupe.add(key)
                    patterns.append(
                        NatalAspectPattern(
                            pattern="grand_trine",
                            bodies=list(key[1]),
                            confidence=0.9,
                            description="Three-way trine circuit indicates fluent talent flow and effortless patterning.",
                        )
                    )

        for pair in oppositions:
            a, b = sorted(pair)
            for c in bodies:
                if c in {a, b}:
                    continue
                if frozenset({a, c}) in squares and frozenset({b, c}) in squares:
                    key = ("t_square", tuple(sorted((a, b, c))))
                    if key in dedupe:
                        continue
                    dedupe.add(key)
                    patterns.append(
                        NatalAspectPattern(
                            pattern="t_square",
                            bodies=list(key[1]),
                            confidence=0.86,
                            description="Opposition plus two squares marks productive tension and strong growth pressure.",
                        )
                    )

        for pattern in [item for item in patterns if item.pattern == "grand_trine"]:
            trio = pattern.bodies
            for d in bodies:
                if d in trio:
                    continue
                for idx, apex in enumerate(trio):
                    others = [trio[(idx + 1) % 3], trio[(idx + 2) % 3]]
                    if (
                        frozenset({d, apex}) in oppositions
                        and frozenset({d, others[0]}) in sextiles
                        and frozenset({d, others[1]}) in sextiles
                    ):
                        key = ("kite", tuple(sorted((d, *trio))))
                        if key in dedupe:
                            continue
                        dedupe.add(key)
                        patterns.append(
                            NatalAspectPattern(
                                pattern="kite",
                                bodies=list(key[1]),
                                confidence=0.82,
                                description="Grand trine anchored by an opposition/sextile axis enables directed output.",
                            )
                        )

        sign_counts: dict[str, list[str]] = {}
        for position in snapshot.positions:
            if position.name not in FOCUS_PLANETS:
                continue
            sign_counts.setdefault(position.sign, []).append(position.name)
        for sign, sign_bodies in sign_counts.items():
            if len(sign_bodies) >= 3:
                key = ("stellium", tuple(sorted(sign_bodies)))
                if key in dedupe:
                    continue
                dedupe.add(key)
                patterns.append(
                    NatalAspectPattern(
                        pattern="stellium",
                        bodies=list(key[1]),
                        confidence=0.74,
                        description=f"Three or more planets in {sign} concentrates expression into one sign archetype.",
                    )
                )

        patterns.sort(key=lambda item: (-item.confidence, item.pattern, ",".join(item.bodies)))
        return patterns
