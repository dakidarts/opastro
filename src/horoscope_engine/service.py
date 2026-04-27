from __future__ import annotations

from datetime import date, datetime, time, timedelta
from itertools import combinations
from pathlib import Path
from typing import List, Optional, Tuple

import swisseph as swe

from .aggregation import aggregate_period
from .config import ServiceConfig, EphemerisConfig
from .content_repository import V2ContentRepository
from .ephemeris import ASPECTS, EphemerisEngine
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
    NatalHouseRulershipInsight,
    NatalHouseRulerPlacement,
    NatalLifeAreaVector,
    NatalTimingOverlay,
    NatalTimingActivation,
    NatalModuleInsight,
    Period,
    PeriodCelestialData,
    PlanetHoroscopeRequest,
    PlanetName,
    ReportType,
    Section,
    AyanamsaSystem,
    HouseSystem,
    NodeType,
    SynastryRequest,
    SynastryResponse,
    SynastryAspect,
    SynastryOverlay,
    SynastryScore,
    TransitTimelineRequest,
    TransitTimelineResponse,
    TransitEvent,
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

HOUSE_AREA_LABELS = {
    1: "identity_direction",
    2: "resources_values",
    3: "communication_learning",
    4: "home_foundation",
    5: "creativity_romance",
    6: "craft_health",
    7: "partnerships",
    8: "shared_assets_transformation",
    9: "vision_belief_growth",
    10: "career_public_role",
    11: "community_networks",
    12: "inner_world_recovery",
}

LIFE_AREA_VECTOR_DEFS: list[tuple[str, list[int]]] = [
    ("self_leadership", [1, 5, 10]),
    ("relationships_collaboration", [5, 7, 11]),
    ("resources_execution", [2, 6, 10]),
    ("emotional_foundation", [4, 8, 12]),
    ("learning_perspective", [3, 9, 11]),
]

TIMING_TRANSIT_WEIGHTS = {"Mars": 1.0, "Jupiter": 0.9, "Saturn": 0.85}
TIMING_NATAL_WEIGHTS = {
    "Sun": 1.0,
    "Moon": 0.95,
    "Mercury": 0.8,
    "Venus": 0.85,
    "Mars": 0.9,
}
TIMING_ASPECT_TARGETS = {
    "conjunction": 0.0,
    "sextile": 60.0,
    "square": 90.0,
    "trine": 120.0,
    "opposition": 180.0,
}
TIMING_ASPECT_WEIGHTS = {
    "conjunction": 1.0,
    "opposition": 0.92,
    "square": 0.88,
    "trine": 0.86,
    "sextile": 0.78,
}


class HoroscopeService:
    def __init__(
        self,
        config: ServiceConfig,
        rules_path: Optional[Path] = None,
    ) -> None:
        self.config = config
        path = (
            rules_path
            or Path(__file__).resolve().parent / "data" / "default_rules.json"
        )
        if not path.exists():
            path = (
                Path(__file__).resolve().parents[2]
                / "data"
                / "rules"
                / "default_rules.json"
            )
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
            AyanamsaSystem.YUKTESWAR: (
                "yukteswar",
                getattr(swe, "SIDM_YUKTESWAR", swe.SIDM_LAHIRI),
            ),
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

    def generate_natal_birthchart(
        self, request: NatalBirthchartRequest
    ) -> NatalBirthchartResponse:
        ephemeris = self._resolve_ephemeris(request)
        include_houses = self._can_use_precise_houses(request.birth)
        coordinates = self._coords_tuple(request.birth) if include_houses else None
        birth_dt = self._birth_datetime(request.birth)
        snapshot = ephemeris.chart_snapshot(
            birth_dt,
            include_houses=include_houses,
            coordinates=coordinates,
            include_fixed_stars=request.include_fixed_stars,
            include_arabic_parts=request.include_arabic_parts,
        )
        planet_conditions = self._natal_planet_conditions(snapshot)
        house_rulership = self._natal_house_rulership(snapshot, planet_conditions)
        premium_insights = NatalPremiumInsights(
            dominant_signature=self._natal_dominant_signature(
                snapshot, planet_conditions
            ),
            aspect_patterns=self._natal_aspect_patterns(snapshot),
            planet_conditions=planet_conditions,
            house_rulership=house_rulership,
            life_area_vectors=self._natal_life_area_vectors(house_rulership),
            timing_overlay=self._natal_timing_overlay(ephemeris, snapshot, birth_dt),
            relationship_module=self._natal_relationship_module(
                snapshot, house_rulership, planet_conditions
            ),
            career_module=self._natal_career_module(
                snapshot, house_rulership, planet_conditions
            ),
        )
        return NatalBirthchartResponse(
            report_type=ReportType.NATAL_BIRTHCHART,
            sign=snapshot.sun_sign,
            birth=request.birth,
            user_name=request.user_name,
            snapshot=snapshot,
            notable_events=self._build_notable_events(snapshot),
            premium_insights=premium_insights,
        )

    def _resolve_sign(
        self,
        sign: Optional[str],
        birth: Optional[BirthData],
        ephemeris: EphemerisEngine,
    ) -> str:
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
        request: HoroscopeRequest
        | BirthdayHoroscopeRequest
        | PlanetHoroscopeRequest
        | NatalBirthchartRequest,
    ) -> EphemerisEngine:
        if (
            not request.zodiac_system
            and not request.ayanamsa
            and not request.house_system
            and not request.node_type
        ):
            return self._default_ephemeris

        base = self.config.ephemeris
        ayanamsa_system = request.ayanamsa or AyanamsaSystem.LAHIRI
        ayanamsa_key, sidereal_mode = self._ayanamsa_map[ayanamsa_system]
        house_system = self._house_map.get(
            request.house_system or HouseSystem.PLACIDUS, base.house_system
        )
        node_type = (request.node_type or NodeType.TRUE).value
        zodiac_system = (
            request.zodiac_system or ZodiacSystem(base.zodiac_system)
        ).value

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

    def _resolve_birthday_range(
        self, birth: Optional[BirthData], target_date: Optional[date]
    ) -> Tuple[datetime, datetime]:
        if birth:
            base = target_date or date.today()
            month = birth.date.month
            day = birth.date.day
            start_date = self._safe_anniversary(base.year, month, day)
            if base < start_date:
                start_date = self._safe_anniversary(base.year - 1, month, day)
        else:
            if target_date is None:
                raise ValueError(
                    "For birthday reports, provide birth data or target_date."
                )
            start_date = target_date
            month = start_date.month
            day = start_date.day

        end_date = self._safe_anniversary(start_date.year + 1, month, day)
        return datetime.combine(start_date, time.min), datetime.combine(
            end_date, time.min
        )

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

    def _coords_tuple(
        self, birth: Optional[BirthData]
    ) -> Optional[Tuple[float, float]]:
        if not birth or not birth.coordinates:
            return None
        return (birth.coordinates.latitude, birth.coordinates.longitude)

    def _resolve_period_range(
        self, period: Period, target_date: Optional[date]
    ) -> Tuple[datetime, datetime]:
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

    def _apply_house_frame(
        self, snapshot: ChartSnapshot, natal_frame: ChartSnapshot
    ) -> None:
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

    def _natal_planet_conditions(
        self, snapshot: ChartSnapshot
    ) -> List[NatalPlanetCondition]:
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
        positions = [
            position
            for position in snapshot.positions
            if position.name in FOCUS_PLANETS
        ]
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

        dominant_element = max(
            element_balance, key=lambda key: (element_balance[key], key)
        )
        dominant_modality = max(
            modality_balance, key=lambda key: (modality_balance[key], key)
        )
        top_planets = [entry.planet for entry in planet_conditions[:3]]

        return NatalDominantSignature(
            element_balance=element_balance,
            modality_balance=modality_balance,
            dominant_element=dominant_element,
            dominant_modality=dominant_modality,
            angular_emphasis=angular_counts,
            top_planets=top_planets,
        )

    def _natal_aspect_patterns(
        self, snapshot: ChartSnapshot
    ) -> List[NatalAspectPattern]:
        bodies = sorted(
            {
                position.name
                for position in snapshot.positions
                if position.name in FOCUS_PLANETS
            }
        )
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

        patterns.sort(
            key=lambda item: (-item.confidence, item.pattern, ",".join(item.bodies))
        )
        return patterns

    def _natal_house_rulership(
        self,
        snapshot: ChartSnapshot,
        planet_conditions: List[NatalPlanetCondition],
    ) -> List[NatalHouseRulershipInsight]:
        positions_by_name = {
            position.name: position
            for position in snapshot.positions
            if position.name in FOCUS_PLANETS
        }
        strength_by_planet = {
            condition.planet: condition.strength for condition in planet_conditions
        }
        house_signs, estimated = self._natal_house_signs(snapshot)

        output: List[NatalHouseRulershipInsight] = []
        for house in range(1, 13):
            cusp_sign = house_signs[house - 1]
            rulers = sorted(SIGN_RULERS.get(cusp_sign, set()))
            ruler_placements: List[NatalHouseRulerPlacement] = []
            ruler_strengths: List[float] = []
            notes: List[str] = []

            for ruler in rulers:
                position = positions_by_name.get(ruler)
                if not position:
                    continue
                strength = strength_by_planet.get(ruler, 1.0)
                ruler_strengths.append(strength)
                ruler_placements.append(
                    NatalHouseRulerPlacement(
                        planet=ruler,
                        sign=position.sign,
                        house=position.house,
                        retrograde=position.retrograde,
                        strength=round(strength, 3),
                    )
                )

            occupants = self._house_occupants(snapshot, house, cusp_sign)
            if occupants:
                notes.append("Occupants: " + ", ".join(sorted(occupants)))

            if ruler_placements:
                placement_labels = ", ".join(
                    f"{item.planet} h{item.house}"
                    if item.house
                    else f"{item.planet} in {item.sign}"
                    for item in ruler_placements
                )
                notes.append("Ruler placement: " + placement_labels)

            if estimated:
                notes.append(
                    "Estimated house wheel (missing exact birth time and/or coordinates)."
                )

            angular_weight = (
                1.0
                if house in {1, 4, 7, 10}
                else 0.7
                if house in {2, 5, 8, 11}
                else 0.5
            )
            occupancy_score = min(1.0, len(occupants) / 3.0)
            ruler_score = (
                min(1.0, (sum(ruler_strengths) / len(ruler_strengths)) / 1.8)
                if ruler_strengths
                else 0.45
            )
            emphasis = (
                0.20
                + (0.45 * ruler_score)
                + (0.25 * occupancy_score)
                + (0.10 * angular_weight)
            )

            output.append(
                NatalHouseRulershipInsight(
                    house=house,
                    area=HOUSE_AREA_LABELS[house],
                    cusp_sign=cusp_sign,
                    rulers=rulers,
                    ruler_placements=ruler_placements,
                    emphasis=round(self._clamp(emphasis, 0.0, 1.0), 3),
                    notes=notes,
                )
            )

        return output

    def _natal_house_signs(self, snapshot: ChartSnapshot) -> tuple[list[str], bool]:
        if snapshot.house_cusps and len(snapshot.house_cusps) == 12:
            return [
                self._sign_from_longitude(cusp) for cusp in snapshot.house_cusps
            ], False

        if snapshot.rising_sign and snapshot.rising_sign in ZODIAC_SIGNS:
            start_idx = ZODIAC_SIGNS.index(snapshot.rising_sign)
            return [ZODIAC_SIGNS[(start_idx + idx) % 12] for idx in range(12)], True

        start_idx = ZODIAC_SIGNS.index(snapshot.sun_sign)
        return [ZODIAC_SIGNS[(start_idx + idx) % 12] for idx in range(12)], True

    def _house_occupants(
        self, snapshot: ChartSnapshot, house: int, cusp_sign: str
    ) -> list[str]:
        occupants: list[str] = []
        for position in snapshot.positions:
            if position.name not in FOCUS_PLANETS:
                continue
            if position.house is not None:
                if position.house == house:
                    occupants.append(position.name)
                continue
            if position.sign == cusp_sign:
                occupants.append(position.name)
        return occupants

    def _sign_from_longitude(self, longitude: float) -> str:
        return ZODIAC_SIGNS[int((longitude % 360.0) // 30)]

    def _natal_life_area_vectors(
        self,
        house_rulership: List[NatalHouseRulershipInsight],
    ) -> List[NatalLifeAreaVector]:
        by_house = {entry.house: entry for entry in house_rulership}
        vectors: List[NatalLifeAreaVector] = []
        for area, houses in LIFE_AREA_VECTOR_DEFS:
            selected = [by_house[house] for house in houses if house in by_house]
            if not selected:
                continue
            avg_emphasis = sum(entry.emphasis for entry in selected) / len(selected)
            score = round(avg_emphasis * 100.0, 1)
            drivers = [
                f"House {entry.house} ({entry.cusp_sign})"
                for entry in sorted(
                    selected, key=lambda item: (-item.emphasis, item.house)
                )[:2]
            ]
            vectors.append(
                NatalLifeAreaVector(
                    area=area,
                    houses=houses,
                    score=score,
                    emphasis=self._score_band(score),
                    drivers=drivers,
                )
            )
        vectors.sort(key=lambda item: (-item.score, item.area))
        return vectors

    def _natal_timing_overlay(
        self,
        ephemeris: EphemerisEngine,
        snapshot: ChartSnapshot,
        birth_dt: datetime,
    ) -> NatalTimingOverlay:
        natal_positions = {
            position.name: position.longitude
            for position in snapshot.positions
            if position.name in TIMING_NATAL_WEIGHTS
        }
        if not natal_positions:
            return NatalTimingOverlay(generated_for=date.today(), activations=[])

        base_date = date.today()
        base_dt = datetime.combine(
            base_date, time(hour=birth_dt.hour, minute=birth_dt.minute)
        )
        candidates: list[tuple[float, date, str, str, str, float]] = []
        seen: set[tuple[date, str, str, str]] = set()
        orb_limit = 1.2

        for day_offset in range(0, 181, 3):
            transit_date = base_dt + timedelta(days=day_offset)
            transit_snapshot = ephemeris.chart_snapshot(
                transit_date, include_houses=False
            )
            transits = {
                position.name: position.longitude
                for position in transit_snapshot.positions
                if position.name in TIMING_TRANSIT_WEIGHTS
            }
            for transit_planet, transit_longitude in transits.items():
                for natal_planet, natal_longitude in natal_positions.items():
                    angle = abs(transit_longitude - natal_longitude)
                    if angle > 180.0:
                        angle = 360.0 - angle
                    for aspect, target in TIMING_ASPECT_TARGETS.items():
                        orb = abs(angle - target)
                        if orb > orb_limit:
                            continue
                        key = (
                            transit_date.date(),
                            transit_planet,
                            natal_planet,
                            aspect,
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        intensity = (
                            (1.0 - (orb / orb_limit))
                            * TIMING_TRANSIT_WEIGHTS[transit_planet]
                            * TIMING_NATAL_WEIGHTS[natal_planet]
                            * TIMING_ASPECT_WEIGHTS[aspect]
                        )
                        candidates.append(
                            (
                                intensity,
                                transit_date.date(),
                                transit_planet,
                                natal_planet,
                                aspect,
                                orb,
                            )
                        )

        activations: List[NatalTimingActivation] = []
        for intensity, hit_date, transit_planet, natal_planet, aspect, orb in sorted(
            candidates, key=lambda item: (-item[0], item[1], item[2], item[3], item[4])
        )[:12]:
            start_date = max(base_date, hit_date - timedelta(days=1))
            end_date = hit_date + timedelta(days=1)
            summary = self._timing_summary(transit_planet, natal_planet, aspect)
            activations.append(
                NatalTimingActivation(
                    start_date=start_date,
                    end_date=end_date,
                    transit_planet=transit_planet,
                    natal_planet=natal_planet,
                    aspect=aspect,
                    orb=round(orb, 2),
                    intensity=round(self._clamp(intensity, 0.0, 1.0), 3),
                    summary=summary,
                )
            )

        return NatalTimingOverlay(generated_for=base_date, activations=activations)

    def _timing_summary(
        self, transit_planet: str, natal_planet: str, aspect: str
    ) -> str:
        aspect_meaning = {
            "conjunction": "amplifies and concentrates",
            "sextile": "opens practical opportunities for",
            "square": "creates pressure that upgrades",
            "trine": "supports fluent progress in",
            "opposition": "reveals balancing lessons around",
        }
        return (
            f"{transit_planet} {aspect} natal {natal_planet} "
            f"{aspect_meaning.get(aspect, 'activates')} this theme."
        )

    def _natal_relationship_module(
        self,
        snapshot: ChartSnapshot,
        house_rulership: List[NatalHouseRulershipInsight],
        planet_conditions: List[NatalPlanetCondition],
    ) -> NatalModuleInsight:
        condition_by_planet = {
            condition.planet: condition for condition in planet_conditions
        }
        relation_planets = [
            name for name in ["Venus", "Mars", "Moon"] if name in condition_by_planet
        ]
        relation_strength = (
            sum(condition_by_planet[name].strength for name in relation_planets)
            / len(relation_planets)
            if relation_planets
            else 1.0
        )

        house7 = next((entry for entry in house_rulership if entry.house == 7), None)
        house5 = next((entry for entry in house_rulership if entry.house == 5), None)
        house8 = next((entry for entry in house_rulership if entry.house == 8), None)
        house_emphasis = (
            (house7.emphasis if house7 else 0.55)
            + (house5.emphasis if house5 else 0.5)
            + (house8.emphasis if house8 else 0.5)
        ) / 3.0

        supportive = 0
        tension = 0
        for aspect in snapshot.aspects:
            pair = {aspect.body1, aspect.body2}
            if pair not in ({"Venus", "Mars"}, {"Venus", "Moon"}, {"Mars", "Moon"}):
                continue
            if aspect.aspect in {"conjunction", "trine", "sextile"}:
                supportive += 1
            if aspect.aspect in {"square", "opposition"}:
                tension += 1

        score = (
            50.0
            + ((relation_strength - 1.0) * 25.0)
            + ((house_emphasis - 0.5) * 30.0)
            + (supportive * 5.5)
            - (tension * 4.0)
        )
        score = round(self._clamp(score, 0.0, 100.0), 1)

        highlights = [
            f"Partnership axis emphasis ({round((house7.emphasis if house7 else 0.5) * 100, 1)}).",
            f"Relational planet condition baseline: {round(relation_strength, 2)}.",
        ]
        if supportive:
            highlights.append(f"Supportive Venus/Mars/Moon aspect count: {supportive}.")

        cautions = []
        if tension:
            cautions.append(
                f"Relational tension aspect count: {tension}; pace emotional reactions."
            )
        if house8 and house8.emphasis >= 0.7:
            cautions.append(
                "High 8th-house emphasis can intensify trust and boundary topics."
            )
        if not cautions:
            cautions.append(
                "Low-friction profile still benefits from direct expectations and pacing."
            )

        actions = [
            "Name one relationship priority and one non-negotiable boundary for this cycle.",
            "Use weekly check-ins to convert emotional assumptions into explicit agreements.",
        ]

        return NatalModuleInsight(
            score=score, highlights=highlights, cautions=cautions, actions=actions
        )

    def _natal_career_module(
        self,
        snapshot: ChartSnapshot,
        house_rulership: List[NatalHouseRulershipInsight],
        planet_conditions: List[NatalPlanetCondition],
    ) -> NatalModuleInsight:
        condition_by_planet = {
            condition.planet: condition for condition in planet_conditions
        }
        career_planets = [
            name
            for name in ["Sun", "Saturn", "Jupiter", "Mercury"]
            if name in condition_by_planet
        ]
        career_strength = (
            sum(condition_by_planet[name].strength for name in career_planets)
            / len(career_planets)
            if career_planets
            else 1.0
        )

        house10 = next((entry for entry in house_rulership if entry.house == 10), None)
        house6 = next((entry for entry in house_rulership if entry.house == 6), None)
        house2 = next((entry for entry in house_rulership if entry.house == 2), None)
        house_emphasis = (
            (house10.emphasis if house10 else 0.55)
            + (house6.emphasis if house6 else 0.5)
            + (house2.emphasis if house2 else 0.5)
        ) / 3.0

        supportive = 0
        friction = 0
        for aspect in snapshot.aspects:
            pair = {aspect.body1, aspect.body2}
            if pair.isdisjoint({"Sun", "Saturn", "Jupiter", "Mercury"}):
                continue
            if aspect.aspect in {"conjunction", "trine", "sextile"}:
                supportive += 1
            if aspect.aspect in {"square", "opposition"}:
                friction += 1

        score = (
            52.0
            + ((career_strength - 1.0) * 24.0)
            + ((house_emphasis - 0.5) * 32.0)
            + (supportive * 2.0)
            - (friction * 1.4)
        )
        score = round(self._clamp(score, 0.0, 100.0), 1)

        highlights = [
            f"Career axis emphasis ({round((house10.emphasis if house10 else 0.5) * 100, 1)}).",
            f"Execution baseline from Sun/Saturn/Jupiter/Mercury: {round(career_strength, 2)}.",
        ]
        if supportive:
            highlights.append(f"Supportive career-planet aspect count: {supportive}.")

        cautions = []
        if friction:
            cautions.append(
                f"Career friction aspect count: {friction}; sequence workload by priority."
            )
        if house6 and house6.emphasis >= 0.7:
            cautions.append(
                "Heavy 6th-house emphasis rewards systems over heroic effort."
            )
        if not cautions:
            cautions.append(
                "Stable signatures still improve with explicit milestones and review loops."
            )

        actions = [
            "Set one visible deliverable for the next 14 days and define its completion metric.",
            "Align calendar blocks with your strongest work window before adding new commitments.",
        ]

        return NatalModuleInsight(
            score=score, highlights=highlights, cautions=cautions, actions=actions
        )

    def generate_synastry(self, request: SynastryRequest) -> SynastryResponse:
        ephemeris = self._resolve_ephemeris(request)
        birth1_dt = self._birth_datetime(request.birth1)
        birth2_dt = self._birth_datetime(request.birth2)

        snapshot1 = ephemeris.chart_snapshot(
            birth1_dt,
            include_houses=self._can_use_precise_houses(request.birth1),
            coordinates=self._coords_tuple(request.birth1),
        )
        snapshot2 = ephemeris.chart_snapshot(
            birth2_dt,
            include_houses=self._can_use_precise_houses(request.birth2),
            coordinates=self._coords_tuple(request.birth2),
        )

        inter_aspects = self._synastry_inter_aspects(snapshot1, snapshot2)
        house_overlays = self._synastry_house_overlays(snapshot1, snapshot2)
        scores = self._synastry_scores(inter_aspects, house_overlays)

        composite_summary = self._synastry_composite_summary(
            snapshot1, snapshot2, inter_aspects, scores
        )

        return SynastryResponse(
            report_type=ReportType.NATAL_BIRTHCHART,
            user_name1=request.user_name1,
            user_name2=request.user_name2,
            snapshot1=snapshot1,
            snapshot2=snapshot2,
            inter_aspects=inter_aspects,
            house_overlays=house_overlays,
            scores=scores,
            composite_summary=composite_summary,
        )

    def _synastry_inter_aspects(
        self, snap1: ChartSnapshot, snap2: ChartSnapshot
    ) -> List[SynastryAspect]:
        aspects: List[SynastryAspect] = []
        bodies1 = {
            p.name: p.longitude for p in snap1.positions if p.name in FOCUS_PLANETS
        }
        bodies2 = {
            p.name: p.longitude for p in snap2.positions if p.name in FOCUS_PLANETS
        }

        for name1, lon1 in bodies1.items():
            for name2, lon2 in bodies2.items():
                angle = abs(lon1 - lon2)
                if angle > 180:
                    angle = 360 - angle
                for aspect_name, (target, tier) in ASPECTS.items():
                    if tier == "sextile":
                        orb_limit = self.config.ephemeris.orb_sextile
                    elif tier == "minor":
                        orb_limit = self.config.ephemeris.orb_minor
                    else:
                        orb_limit = self.config.ephemeris.orb_major
                    diff = abs(angle - target)
                    if diff <= orb_limit:
                        nature = (
                            "supportive"
                            if aspect_name in {"conjunction", "trine", "sextile"}
                            else "challenging"
                        )
                        aspects.append(
                            SynastryAspect(
                                body1=name1,
                                body2=name2,
                                aspect=aspect_name,
                                orb=round(diff, 2),
                                exact=diff <= self.config.ephemeris.aspect_exact_orb,
                                applying=False,
                                nature=nature,
                            )
                        )
        aspects.sort(key=lambda a: (a.nature != "supportive", a.orb))
        return aspects

    def _synastry_house_overlays(
        self, snap1: ChartSnapshot, snap2: ChartSnapshot
    ) -> List[SynastryOverlay]:
        overlays: List[SynastryOverlay] = []
        if not snap1.house_cusps or len(snap1.house_cusps) != 12:
            return overlays

        for house in range(1, 13):
            cusp_sign = self._sign_from_longitude(snap1.house_cusps[house - 1])
            planets_in_house: List[str] = []
            for position in snap2.positions:
                if position.name not in FOCUS_PLANETS:
                    continue
                if position.house == house:
                    planets_in_house.append(position.name)
            if planets_in_house:
                overlays.append(
                    SynastryOverlay(
                        house=house,
                        cusp_sign=cusp_sign,
                        planets=planets_in_house,
                        interpretation_hint=f"Partner's {', '.join(planets_in_house)} in your house {house} ({HOUSE_AREA_LABELS.get(house, '')}).",
                    )
                )
        return overlays

    def _synastry_scores(
        self,
        inter_aspects: List[SynastryAspect],
        house_overlays: List[SynastryOverlay],
    ) -> List[SynastryScore]:
        supportive = sum(1 for a in inter_aspects if a.nature == "supportive")
        challenging = sum(1 for a in inter_aspects if a.nature == "challenging")
        total = max(1, supportive + challenging)
        harmony = round((supportive / total) * 100, 1)
        intensity = round(min(100.0, len(inter_aspects) * 3.5), 1)

        return [
            SynastryScore(
                category="harmony",
                score=harmony,
                emphasis=self._score_band(harmony),
            ),
            SynastryScore(
                category="intensity",
                score=intensity,
                emphasis=self._score_band(intensity),
            ),
            SynastryScore(
                category="house_overlays",
                score=min(100.0, len(house_overlays) * 12.5),
                emphasis=self._score_band(min(100.0, len(house_overlays) * 12.5)),
            ),
        ]

    def _synastry_composite_summary(
        self,
        snap1: ChartSnapshot,
        snap2: ChartSnapshot,
        inter_aspects: List[SynastryAspect],
        scores: List[SynastryScore],
    ) -> str:
        harmony = next((s for s in scores if s.category == "harmony"), None)
        if harmony and harmony.score >= 70:
            tone = "strong natural resonance"
        elif harmony and harmony.score >= 50:
            tone = "balanced dynamic with growth edges"
        else:
            tone = "intense mirroring with work required"
        return (
            f"{snap1.sun_sign} meets {snap2.sun_sign}: {tone}. "
            f"{len(inter_aspects)} inter-chart aspects detected."
        )

    def generate_transit_timeline(
        self, request: TransitTimelineRequest
    ) -> TransitTimelineResponse:
        ephemeris = self._resolve_ephemeris(request)
        include_houses = self._can_use_precise_houses(request.birth)
        coordinates = self._coords_tuple(request.birth) if include_houses else None
        birth_dt = self._birth_datetime(request.birth)

        natal_snapshot = ephemeris.chart_snapshot(
            birth_dt,
            include_houses=include_houses,
            coordinates=coordinates,
        )

        date_from = request.date_from or date.today()
        date_to = request.date_to or (date_from + timedelta(days=90))

        natal_positions = {
            p.name: p.longitude
            for p in natal_snapshot.positions
            if p.name in TIMING_NATAL_WEIGHTS
        }

        events: List[TransitEvent] = []
        seen: set[tuple[date, str, str, str]] = set()
        orb_limit = 1.5

        current = date_from
        while current <= date_to:
            current_dt = datetime.combine(
                current, time(hour=birth_dt.hour, minute=birth_dt.minute)
            )
            transit_snapshot = ephemeris.chart_snapshot(
                current_dt, include_houses=False
            )
            transits = {
                p.name: p.longitude
                for p in transit_snapshot.positions
                if p.name in TIMING_TRANSIT_WEIGHTS
            }
            for transit_planet, transit_lon in transits.items():
                for natal_planet, natal_lon in natal_positions.items():
                    angle = abs(transit_lon - natal_lon)
                    if angle > 180.0:
                        angle = 360.0 - angle
                    for aspect, target in TIMING_ASPECT_TARGETS.items():
                        orb = abs(angle - target)
                        if orb > orb_limit:
                            continue
                        key = (current, transit_planet, natal_planet, aspect)
                        if key in seen:
                            continue
                        seen.add(key)
                        intensity = (
                            (1.0 - (orb / orb_limit))
                            * TIMING_TRANSIT_WEIGHTS[transit_planet]
                            * TIMING_NATAL_WEIGHTS[natal_planet]
                            * TIMING_ASPECT_WEIGHTS[aspect]
                        )
                        events.append(
                            TransitEvent(
                                date=current,
                                transit_planet=transit_planet,
                                natal_planet=natal_planet,
                                aspect=aspect,
                                orb=round(orb, 2),
                                exact=orb <= self.config.ephemeris.aspect_exact_orb,
                                intensity=round(self._clamp(intensity, 0.0, 1.0), 3),
                                summary=self._timing_summary(
                                    transit_planet, natal_planet, aspect
                                ),
                            )
                        )
            current += timedelta(days=1)

        events.sort(
            key=lambda e: (-e.intensity, e.date, e.transit_planet, e.natal_planet)
        )

        return TransitTimelineResponse(
            birth=request.birth,
            date_from=date_from,
            date_to=date_to,
            events=events,
            event_count=len(events),
        )

    def _score_band(self, score: float) -> str:
        if score >= 75.0:
            return "high"
        if score >= 60.0:
            return "elevated"
        if score >= 45.0:
            return "steady"
        return "quiet"

    def _clamp(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))
