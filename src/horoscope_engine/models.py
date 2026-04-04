from __future__ import annotations

from datetime import datetime, date
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


class Period(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class Section(str, Enum):
    GENERAL = "general"
    LOVE_SINGLES = "love_singles"
    LOVE_COUPLES = "love_couples"
    CAREER = "career"
    FRIENDSHIP = "friendship"
    HEALTH = "health"
    MONEY = "money"
    COMMUNICATION = "communication"
    LIFESTYLE = "lifestyle"


class AyanamsaSystem(str, Enum):
    LAHIRI = "lahiri"
    FAGAN_BRADLEY = "fagan_bradley"
    KRISHNAMURTI = "krishnamurti"
    RAMAN = "raman"
    YUKTESWAR = "yukteswar"


class HouseSystem(str, Enum):
    PLACIDUS = "placidus"
    WHOLE_SIGN = "whole_sign"
    EQUAL = "equal"
    KOCH = "koch"


class NodeType(str, Enum):
    TRUE = "true"
    MEAN = "mean"


class ZodiacSystem(str, Enum):
    SIDEREAL = "sidereal"
    TROPICAL = "tropical"


class ReportType(str, Enum):
    HOROSCOPE = "horoscope"
    BIRTHDAY = "birthday"
    PLANET = "planet"
    NATAL_BIRTHCHART = "natal_birthchart"


class PlanetName(str, Enum):
    SUN = "sun"
    MOON = "moon"
    MERCURY = "mercury"
    VENUS = "venus"
    MARS = "mars"
    JUPITER = "jupiter"
    SATURN = "saturn"
    URANUS = "uranus"
    NEPTUNE = "neptune"
    PLUTO = "pluto"
    CHIRON = "chiron"


ZODIAC_SIGNS = [
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


class Coordinates(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class BirthData(BaseModel):
    date: date
    time: Optional[str] = Field(
        default=None,
        description="HH:MM (24h). If omitted, noon is assumed.",
    )
    coordinates: Optional[Coordinates] = None
    timezone: Optional[str] = None


class HoroscopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: Period
    sign: Optional[str] = Field(default=None, description="Zodiac sign name")
    target_date: Optional[date] = None
    birth: Optional[BirthData] = None
    sections: Optional[List[Section]] = None
    zodiac_system: Optional[ZodiacSystem] = None
    ayanamsa: Optional[AyanamsaSystem] = None
    house_system: Optional[HouseSystem] = None
    node_type: Optional[NodeType] = None
    tenant_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("sign")
    @classmethod
    def normalize_sign(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().upper()
        if normalized not in ZODIAC_SIGNS:
            raise ValueError("Unsupported zodiac sign")
        return normalized

    @field_validator("sections", mode="before")
    @classmethod
    def reject_legacy_love_section(cls, value):
        if value is None:
            return value
        entries = value if isinstance(value, list) else [value]
        for entry in entries:
            raw = entry.value if isinstance(entry, Section) else str(entry)
            if raw.strip().lower() == "love":
                raise ValueError("Section 'love' is no longer supported. Use 'love_singles' and/or 'love_couples'.")
        return value


class BirthdayHoroscopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sign: Optional[str] = Field(default=None, description="Zodiac sign name")
    target_date: Optional[date] = Field(
        default=None,
        description=(
            "Birthday cycle anchor date. If birth data is provided, this date decides which birthday cycle "
            "to render; otherwise it is treated as the birthday date."
        ),
    )
    birth: Optional[BirthData] = None
    sections: Optional[List[Section]] = None
    zodiac_system: Optional[ZodiacSystem] = None
    ayanamsa: Optional[AyanamsaSystem] = None
    house_system: Optional[HouseSystem] = None
    node_type: Optional[NodeType] = None
    tenant_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("sign")
    @classmethod
    def normalize_sign(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().upper()
        if normalized not in ZODIAC_SIGNS:
            raise ValueError("Unsupported zodiac sign")
        return normalized

    @field_validator("sections", mode="before")
    @classmethod
    def reject_legacy_love_section(cls, value):
        if value is None:
            return value
        entries = value if isinstance(value, list) else [value]
        for entry in entries:
            raw = entry.value if isinstance(entry, Section) else str(entry)
            if raw.strip().lower() == "love":
                raise ValueError("Section 'love' is no longer supported. Use 'love_singles' and/or 'love_couples'.")
        return value


class PlanetHoroscopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: Period
    planet: PlanetName
    sign: Optional[str] = Field(default=None, description="Zodiac sign name")
    target_date: Optional[date] = None
    birth: Optional[BirthData] = None
    sections: Optional[List[Section]] = None
    zodiac_system: Optional[ZodiacSystem] = None
    ayanamsa: Optional[AyanamsaSystem] = None
    house_system: Optional[HouseSystem] = None
    node_type: Optional[NodeType] = None
    tenant_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("sign")
    @classmethod
    def normalize_sign(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().upper()
        if normalized not in ZODIAC_SIGNS:
            raise ValueError("Unsupported zodiac sign")
        return normalized

    @field_validator("sections", mode="before")
    @classmethod
    def reject_legacy_love_section(cls, value):
        if value is None:
            return value
        entries = value if isinstance(value, list) else [value]
        for entry in entries:
            raw = entry.value if isinstance(entry, Section) else str(entry)
            if raw.strip().lower() == "love":
                raise ValueError("Section 'love' is no longer supported. Use 'love_singles' and/or 'love_couples'.")
        return value


class NatalBirthchartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    birth: BirthData
    zodiac_system: Optional[ZodiacSystem] = None
    ayanamsa: Optional[AyanamsaSystem] = None
    house_system: Optional[HouseSystem] = None
    node_type: Optional[NodeType] = None
    tenant_id: Optional[str] = Field(default=None, max_length=64)


class BodyPosition(BaseModel):
    name: str
    longitude: float
    tropical_longitude: float
    sidereal_longitude: float
    latitude: float
    speed: float
    sign: str
    tropical_sign: str
    sidereal_sign: str
    degree_in_sign: float
    house: Optional[int] = None
    retrograde: bool
    ayanamsa_value: float


class Aspect(BaseModel):
    body1: str
    body2: str
    aspect: str
    orb: float
    exact: bool
    applying: bool


class ChartSnapshot(BaseModel):
    timestamp: datetime
    zodiac_system: str
    ayanamsa: str
    ayanamsa_value: float
    ayanamsa_system: str
    sun_sign: str
    moon_sign: str
    rising_sign: Optional[str] = None
    house_system: Optional[str] = None
    house_cusps: Optional[List[float]] = None
    positions: List[BodyPosition]
    aspects: List[Aspect]


class PeriodEvent(BaseModel):
    timestamp: datetime
    event_type: str
    body1: Optional[str] = None
    body2: Optional[str] = None
    sign: Optional[str] = None
    aspect: Optional[str] = None
    exactness: Optional[float] = None
    narrative_priority: float = 0.0
    section_bias: Dict[str, float] = Field(default_factory=dict)
    description: str


class PeriodCelestialData(BaseModel):
    period: Period
    start: datetime
    end: datetime
    snapshot: ChartSnapshot
    metrics: Optional["PeriodMetrics"] = None
    notable_events: List[str] = Field(default_factory=list)
    period_events: List[PeriodEvent] = Field(default_factory=list)
    factor_values: Dict[str, str] = Field(default_factory=dict)


class PeriodMetrics(BaseModel):
    sample_count: int
    aspect_counts: Dict[str, int]
    retrograde_bodies: List[str]
    sign_changes: List[str]


class FactorDetail(BaseModel):
    factor_type: str
    factor_value: str
    weight: float
    factor_insights: Dict[str, str] = Field(default_factory=dict)


class SectionInsight(BaseModel):
    section: Section
    title: str
    summary: str
    highlights: List[str]
    cautions: List[str]
    actions: List[str]
    scores: Dict[str, float]
    intensity: str
    factor_details: List[FactorDetail] = Field(default_factory=list)


class HoroscopeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_type: ReportType = ReportType.HOROSCOPE
    sign: str
    period: Period
    start: datetime
    end: datetime
    data: PeriodCelestialData
    sections: List[SectionInsight]


class NatalBirthchartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_type: ReportType = ReportType.NATAL_BIRTHCHART
    sign: str
    birth: BirthData
    snapshot: ChartSnapshot
    notable_events: List[str] = Field(default_factory=list)


class PregenRequest(BaseModel):
    period: Period
    target_date: date
    tenant_id: Optional[str] = None
